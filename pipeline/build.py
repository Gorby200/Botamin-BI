"""Pipeline orchestrator.

Flow:
  1. Ingest (Google Sheets export or local CSV/XLSX).
  2. Profile.
  3. Classify every call with the DETERMINISTIC engine (failsafe) — always runs.
  4. Overlay the LLM engine on the selected scope (focus/full/sample) IF a key is
     configured. LLM results replace deterministic ones per-call (same contract).
  5. Flatten the unified analysis contract into a DataFrame.
  6. Compute the two-layer metric model + diagnostics + ranked backlog.
  7. Write the JSON contract for the React SPA, including LLM status and the
     audio-instrumentation spec (metrics that require the original recording).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import settings
from .ingest import ingest_sheet, ingest_file
from .profile import profile_data, parse_duration_seconds, Profile
from .stages import classify_dialogue, _parse_turns
from .metrics import compute_metrics
from .diagnostics import (
    audit_bot_patterns, cluster_objections, analyze_pitch, generate_backlog,
)
from .custdev import build_custdev
from .patterns import pattern_meta


logger = logging.getLogger(__name__)


# ── Audio-instrumentation spec (the "extract from the original recording" page) ──
# These metrics are CRITICAL but CANNOT be derived from the text transcript alone.
# The dashboard shows them as locked, with WHY each matters, so the data contract
# at the source can be upgraded.
INSTRUMENTATION_SPEC = [
    {
        "id": "latency_to_first_token",
        "name": "Задержка до первой реплики бота (dead-air)",
        "needs": "Пер-реплик таймстемпы начала/конца речи в записи.",
        "why": "Пауза >1.5–2 с после ответа клиента — главная причина «алло?» и сброса. "
               "Из текста не виден; именно он часто рушит опенер, а не слова.",
        "unlocks": "Корреляция dead-air ↔ early_drop_rate; A/B на скорость отклика.",
    },
    {
        "id": "barge_in_rate",
        "name": "Перебивания (barge-in)",
        "needs": "Флаги наложения речи (клиент заговорил поверх бота) из VAD/диаризации.",
        "why": "Бот, который не умеет замолкать при перебивании, воспринимается как робот и злит. "
               "В тексте перебивание выглядит как обычная реплика.",
        "unlocks": "Метрика «уважение к перебиванию»; правка длины реплик и barge-in policy.",
    },
    {
        "id": "asr_confidence",
        "name": "Уверенность распознавания (ASR confidence)",
        "needs": "Пер-слово/пер-реплика confidence от ASR-движка.",
        "why": "Прямой сигнал «бот не расслышал» ДО того, как клиент скажет «что?». "
               "Наш текстовый repair-rate — лишь поздний прокси.",
        "unlocks": "Ранний детектор обвала связи; авто-перенос звонка; чистка метрик от ASR-шума.",
    },
    {
        "id": "prosody_sentiment",
        "name": "Тон/эмоция клиента (просодия)",
        "needs": "Аудио-фичи: высота тона, темп, громкость, паузы; аудио-сентимент.",
        "why": "Раздражение/интерес слышно в голосе раньше, чем в словах. Текст «да» нейтрален, "
               "а тон может быть ледяным.",
        "unlocks": "Ранний индикатор оттока в разговоре; качество как опережающий показатель.",
    },
    {
        "id": "talk_overlap_silence",
        "name": "Точные talk/listen и доля тишины",
        "needs": "Временные границы речи каждого спикера.",
        "why": "Наш talk-share считается по словам — грубо. Реальная доля времени и паузы точнее "
               "показывают монолог и неловкие молчания.",
        "unlocks": "Честный talk-to-listen во времени; детектор затянутых пауз.",
    },
    {
        "id": "interruption_recovery",
        "name": "Восстановление после сбоя",
        "needs": "Аудио-маркеры повторов + тайминги.",
        "why": "Сколько секунд бот тратит на восстановление после «не слышу» — прямой ущерб AHT и нервам клиента.",
        "unlocks": "Стоимость ASR-петель в секундах; приоритизация телефонных правок.",
    },
]


def _extract_features(row: pd.Series) -> dict:
    """Deterministic enrichment of a single row (always runs — the failsafe)."""
    dialogue = str(row.get("dialogue", "") or "")
    status = row.get("status", None)
    end_reason = row.get("end_reason", None)

    secs = parse_duration_seconds(pd.Series([row.get("duration_raw", "")])).iloc[0]
    duration_sec = float(secs) if secs is not None and not pd.isna(secs) else 0.0

    analysis = classify_dialogue(dialogue, status, end_reason, duration_sec)

    turns = _parse_turns(dialogue)
    bot_turns = [t for t in turns if t["role"] == "bot"]
    client_turns = [t for t in turns if t["role"] == "client"]
    bot_text = " ".join(t["text"] for t in bot_turns)
    client_text_l = " ".join(t["text"].lower() for t in client_turns)

    complaint = bool(re.search(
        r"не\s+звон|уберите\s+номер|отстан|прекратите|\bхватит\b|не\s+беспокой|жалоб",
        client_text_l,
    ))

    dt = pd.to_datetime(row.get("datetime", ""), errors="coerce", format="mixed")
    hour = int(dt.hour) if not pd.isna(dt) else None
    dow = int(dt.dayofweek) if not pd.isna(dt) else None

    return {
        "analysis": analysis,
        "has_dialogue": bool(turns),
        "duration_sec": duration_sec,
        "bot_turns": len(bot_turns),
        "client_turns": len(client_turns),
        "bot_text": bot_text,
        "complaint_signal": complaint,
        "hour": hour,
        "dow": dow,
        "turns": turns,
    }


# Canonical outcomes + stage→outcome map. Applied at FLATTEN time (post-cache,
# deterministic) so an LLM that emits a non-canonical/over-claimed outcome can't leak
# through: every call ends up with exactly one valid outcome → outcomes sum == total rows.
_VALID_OUTCOMES = {"no_contact", "contact_only", "refused", "consent",
                   "offer_engaged", "meeting", "qualified"}
_FS_TO_OUTCOME = {-1: "no_contact", 0: "contact_only", 1: "consent",
                  2: "offer_engaged", 3: "meeting", 4: "qualified"}


def _flatten(analysis: dict) -> dict:
    """Flatten the unified analysis contract into scalar/list columns for metrics."""
    v = analysis.get("voice", {})
    connected = bool(analysis.get("connected", False))
    fs = int(analysis.get("furthest_stage", -1)) if connected else -1
    outcome = str(analysis.get("outcome", "") or "")
    if outcome not in _VALID_OUTCOMES:          # unknown string from the model → derive from stage
        outcome = _FS_TO_OUTCOME.get(fs, "no_contact")
    return {
        "source": analysis.get("source", "deterministic"),
        "connected": connected,
        # Canonical: a non-connected call has NO stage. This keeps the per-call index
        # (furthest_stage >= 0) and the aggregate `engaged` count in exact agreement.
        "furthest_stage": fs,
        "outcome": outcome,
        "disqualified": bool(analysis.get("disqualified", False)),
        "end_attribution": analysis.get("end_attribution", ""),
        "loss_layer": analysis.get("loss_layer", "none"),
        "loss_reason": analysis.get("loss_reason", "other"),
        "asr_breakdown": bool(v.get("asr_breakdown", False)),
        "asr_severity": v.get("asr_severity", "none"),
        "responsiveness": float(v.get("responsiveness", 0.0)),
        "repair_attempts": int(v.get("repair_attempts", 0)),
        "bot_talk_share": float(v.get("bot_talk_share", 0.0)),
        "longest_bot_monologue": int(v.get("longest_bot_monologue_words", 0)),
        "quality_score": float(analysis.get("quality_score", 0.0)),
        "objections": analysis.get("objections", []),
        "bot_patterns": analysis.get("bot_patterns", []),
        "stage_evidence": analysis.get("stage_evidence", {}),
        "summary": analysis.get("summary", ""),
    }


def run_pipeline(
    sheet_url: str | None = None,
    gid: int | None = None,
    file_path: Path | None = None,
    out_dir: Path = Path("frontend/public/data"),
    sample: int | None = None,
    llm_scope: str | None = None,
) -> None:
    print("=" * 64)
    print("Botamin BI Pipeline — Starting")
    print("=" * 64)

    scope = (llm_scope or settings.LLM_SCOPE or "focus").lower()

    # 1. Ingest
    print("\n[1/6] Ingesting data...")
    cache_path = Path("data/raw.csv")
    if sheet_url:
        df = ingest_sheet(sheet_url, gid=gid, cache_path=cache_path)
    elif file_path:
        df = ingest_file(file_path)
    else:
        raise ValueError("Provide sheet_url or file_path")
    if sample:
        df = df.head(sample).reset_index(drop=True)
        print(f"[pipeline] Limited to {sample} rows")
    df = df.reset_index(drop=True)

    # 2. Profile
    print("\n[2/6] Profiling data...")
    profile = profile_data(df)
    print(f"  Rows: {profile.total_rows} | empty dialogue: {profile.empty_dialogue_share:.1%}")

    # 3. Deterministic enrichment (failsafe — always)
    print("\n[3/6] Classifying (deterministic failsafe)...")
    features = [_extract_features(row) for _, row in df.iterrows()]
    call_ids = [f"c_{i:05d}" for i in range(len(df))]

    # 4. LLM single pass — ONE cached call per selected dialogue overlays the
    #    deterministic failsafe with the richer contract (stages + patterns + V4
    #    quality + product-intel). Everything numeric stays deterministic downstream.
    if scope != "off" and settings.llm_configured:
        from pipeline.llm.orchestrator import integrate_with_pipeline

        print(f"\n[4/6] LLM single-pass analysis ({scope})...")
        features, llm_status = integrate_with_pipeline(features, scope)
        print(f"  Analyzed {llm_status.get('calls_analyzed', 0)}/"
              f"{llm_status.get('calls_selected', 0)} selected calls (mode={llm_status.get('mode')})")
        if llm_status.get("note"):
            print(f"  ⚠ {llm_status['note']}")
    else:
        llm_status = {
            "configured": settings.llm_configured, "provider": settings.primary_provider,
            "scope": scope, "mode": "deterministic", "available": False,
            "calls_selected": 0, "calls_analyzed": 0, "note": "",
        }
        print("\n[4/6] LLM disabled (no key or scope=off) — deterministic only.")
        if scope != "off":
            llm_status["note"] = "LLM-ключ не задан в .env — работает детерминированный анализ."

    # 5. Flatten into DataFrame
    flat = pd.DataFrame([_flatten(f["analysis"]) for f in features])
    for col in ["has_dialogue", "duration_sec", "bot_turns", "client_turns",
                "bot_text", "complaint_signal", "hour", "dow"]:
        flat[col] = [f[col] for f in features]
    df = pd.concat([df.reset_index(drop=True), flat.reset_index(drop=True)], axis=1)

    dist = df["outcome"].value_counts().to_dict()
    print(f"  Outcome distribution: { {str(k): int(v) for k, v in dist.items()} }")

    # 6. Metrics + diagnostics + backlog
    print("\n[5/6] Computing metrics + diagnostics...")
    m = compute_metrics(df)
    pattern_audit = audit_bot_patterns(df)
    objection_clusters = cluster_objections(df)
    pitch = analyze_pitch(df)
    base_conv = int(df["connected"].sum())
    backlog = generate_backlog(
        drivers=m["drivers"], nsm=m["nsm"], funnel=m["funnel"],
        pattern_audit=pattern_audit, objection_clusters=objection_clusters,
        loss_attribution=m["loss_attribution"], base_conversations=base_conv,
    )
    # CustDev — voice of the customer. NO separate LLM pass: we REDUCE the per-call
    # product-intel insights already produced by the single analysis pass into the
    # page contract with REAL counts. Falls back to deterministic keyword clustering
    # when the LLM did not run.
    custdev_insights = None
    if scope != "off" and settings.llm_configured:
        per_call: dict[str, list[dict]] = {}
        for i, f in enumerate(features):
            a = f["analysis"]
            if a.get("source") == "llm" and a.get("connected"):
                ins = (a.get("product_intel") or {}).get("insights") or []
                if ins:
                    per_call[f"c_{i:05d}"] = ins
        custdev_insights = per_call or None
        if custdev_insights:
            print(f"  CustDev: reduced product-intel from {len(custdev_insights)} calls")
    custdev = build_custdev(df, features, prompt=settings.CUSTDEV_PROMPT or None,
                            llm_insights=custdev_insights)

    print(f"  Reach: connect={_mval(m['reach']['metrics'],'connect_rate'):.1%} "
          f"engage={_mval(m['reach']['metrics'],'conversation_rate'):.1%}")
    print(f"  NSM QMR: {m['nsm']['value']:.2%}  (meeting_rate={m['nsm']['variants']['meeting_rate']['value']:.2%})")
    for d in m["drivers"]:
        print(f"  {d['id']} {d['name']}: {d['value']:.1%} (in={d['volume_in']})")
    bn = m["bottleneck"]
    if bn:
        print(f"  Bottleneck: {bn['label']} = {bn['conversion']:.1%}")

    # 7. Write JSON
    print(f"\n[6/6] Writing JSON to {out_dir}...")
    _write_outputs(out_dir, df, m, pattern_audit, objection_clusters, pitch,
                   backlog, profile, llm_status, call_ids, features, sheet_url, file_path,
                   custdev)

    print("\n✅ Pipeline complete.")
    _print_summary(m, backlog, llm_status)


def _mval(metrics_list, mid):
    for x in metrics_list:
        if x["id"] == mid:
            return x["value"]
    return 0.0


def _quality_gap_summary(features) -> dict | None:
    """Deterministic V4 quality + outcome + gap distribution over connected calls.

    Numbers are computed here (counts/averages), never by the LLM. The per-call
    `quality` object comes from methodology.quality_from_layers (LLM layers or the
    deterministic approximation) — both engines populate it identically in shape.
    """
    rows = [f["analysis"]["quality"] for f in features
            if f["analysis"].get("connected") and isinstance(f["analysis"].get("quality"), dict)]
    n = len(rows)
    if not n:
        return None
    avg_q = sum(r.get("total", 0.0) for r in rows) / n
    avg_o = sum(r.get("outcome", 0.0) for r in rows) / n
    grades: dict[str, int] = {}
    for r in rows:
        g = r.get("grade", "?")
        grades[g] = grades.get(g, 0) + 1
    closing = sum(1 for r in rows if (r.get("gap") or {}).get("gap", 0) > 1.5)
    warm = sum(1 for r in rows if (r.get("gap") or {}).get("gap", 0) < -1.5)
    aligned = n - closing - warm
    avg_gap = round(avg_q - avg_o, 2)
    if avg_gap > 1.5:
        interp = ("Качество ведения в среднем ВЫШЕ результата: бот хорошо ведёт, но не доводит "
                  "до встречи — узкое место в закрытии или нерелевантная база.")
    elif avg_gap < -1.5:
        interp = ("Результат в среднем ВЫШЕ качества: клиенты доходят несмотря на слабое ведение — "
                  "тёплая база; промпт недоиспользует потенциал.")
    else:
        interp = "Качество ведения в среднем соответствует достигнутому результату."
    return {
        "n": n,
        "avg_quality": round(avg_q, 2),
        "avg_outcome": round(avg_o, 2),
        "avg_gap": avg_gap,
        "grade_distribution": [{"grade": g, "count": grades[g]} for g in sorted(grades)],
        "buckets": {"closing_bottleneck": closing, "warm_base": warm, "aligned": aligned},
        "interpretation": interp,
    }


def _write_outputs(out_dir, df, m, pattern_audit, objection_clusters, pitch,
                   backlog, profile, llm_status, call_ids, features, sheet_url, file_path,
                   custdev=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    calls_dir = out_dir / "calls"
    calls_dir.mkdir(exist_ok=True)

    dashboard = {
        "meta": {
            "source": sheet_url or str(file_path),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "total_rows": profile.total_rows,
            "period_from": profile.date_range[0],
            "period_to": profile.date_range[1],
            "llm": llm_status,
            "data_quality": profile.anomalies,
        },
        "reach": m["reach"],
        "nsm": m["nsm"],
        "funnel": m["funnel"],
        "drivers": m["drivers"],
        "quality": m["quality"],
        "guardrails": m["guardrails"],
        "loss_attribution": m["loss_attribution"],
        "bottleneck": m["bottleneck"],
        "gap_analysis": _quality_gap_summary(features),
        "outcomes": m["outcomes"],
        "time_heatmap": m["time_heatmap"],
        "duration_distribution": m["duration_distribution"],
        "thresholds_defaults": m["thresholds_defaults"],
        "diagnostics": {
            "pattern_audit": pattern_audit,
            "objection_clusters": objection_clusters,
            "pitch": pitch,
        },
        "instrumentation_spec": INSTRUMENTATION_SPEC,
    }
    _write_json(out_dir / "dashboard.json", dashboard)
    _write_json(out_dir / "backlog.json", backlog)
    if custdev is not None:
        _write_json(out_dir / "custdev.json", custdev)

    # Tier 3 research results (if available from three-tier analysis)
    research_results = llm_status.get("tier3_results") if isinstance(llm_status, dict) else None
    if research_results and isinstance(research_results, dict):
        _write_json(out_dir / "research.json", research_results)
        logger.info("  Wrote research.json with Tier 3 insights")

    # calls index with page reference
    PAGE_SIZE = 50
    index = []
    pages = {}  # page_id -> [call_cards]

    for i, (_, row) in enumerate(df.iterrows()):
        page_id = i // PAGE_SIZE
        snippet = str(row.get("dialogue", "") or "")[:140].replace("\n", " ")
        index.append({
            "id": call_ids[i],
            "page": f"page_{page_id:03d}",
            "idx_in_page": i % PAGE_SIZE,
            "datetime": str(row.get("datetime", "")),
            "duration_sec": float(row.get("duration_sec", 0)),
            "status": str(row.get("status", "")),
            "end_attribution": str(row.get("end_attribution", "")),
            "furthest_stage": int(row.get("furthest_stage", -1)),
            "outcome": str(row.get("outcome", "")),
            "loss_layer": str(row.get("loss_layer", "")),
            "asr_severity": str(row.get("asr_severity", "")),
            "responsiveness": float(row.get("responsiveness", 0)),
            "source": str(row.get("source", "")),
            "snippet": snippet,
        })

        # Build full call card
        turns = features[i]["turns"]
        analysis = features[i]["analysis"]
        transcript = [{"role": t["role"], "text": t["text"]} for t in turns]
        card = {
            "id": call_ids[i],
            "datetime": str(row.get("datetime", "")),
            "duration_sec": float(row.get("duration_sec", 0)),
            "status": str(row.get("status", "")),
            "end_reason": str(row.get("end_reason", "")),
            "audio_url": str(row.get("audio_url", "")),
            "furthest_stage": int(row.get("furthest_stage", -1)),
            "outcome": str(row.get("outcome", "")),
            "summary": analysis.get("summary", ""),
            "source": analysis.get("source", "deterministic"),
            "loss_layer": analysis.get("loss_layer", ""),
            "loss_reason": analysis.get("loss_reason", ""),
            "disqualified": analysis.get("disqualified", False),
            "stage_evidence": analysis.get("stage_evidence", {}),
            "voice": analysis.get("voice", {}),
            "detected_patterns": [
                {"id": p.get("id", ""), "polarity": p.get("polarity", ""),
                 "quote": p.get("quote", ""), "name": pattern_meta(p.get("id", "")).get("name", "")}
                for p in analysis.get("bot_patterns", []) if isinstance(p, dict)
            ],
            "objections": analysis.get("objections", []),
            "quality": analysis.get("quality", {}),
            "product_intel": analysis.get("product_intel", {}),
            "recommendations": analysis.get("recommendations", []),
            "transcript": transcript,
        }

        if page_id not in pages:
            pages[page_id] = []
        pages[page_id].append(card)

    _write_json(calls_dir / "index.json", index, compact=True)

    # Write batched page files (50 calls per page)
    page_count = len(pages)
    print(f"  Writing {len(df)} calls in {page_count} pages ({PAGE_SIZE} calls/page)...")
    for page_id in sorted(pages.keys()):
        page_file = calls_dir / f"page_{page_id:03d}.json"
        _write_json(page_file, pages[page_id], compact=True)


def _write_json(path: Path, data, compact: bool = False) -> None:
    """Write JSON to file. Use compact mode for large files (index, pages)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"), default=str)
        else:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _print_summary(m, backlog, llm_status) -> None:
    print("\n" + "=" * 64)
    print("СВОДКА")
    print("=" * 64)
    mode = ("LLM (" + llm_status["provider"] + ")"
            if str(llm_status.get("mode", "")).startswith("llm")
            else "детерминированный (failsafe)")
    print(f"Режим анализа: {mode}")
    if llm_status["note"]:
        print(f"  ⚠ {llm_status['note']}")
    print(f"\nReach: дозвон {_mval(m['reach']['metrics'],'connect_rate'):.1%}, "
          f"вовлечение {_mval(m['reach']['metrics'],'conversation_rate'):.1%}")
    print(f"NSM QMR: {m['nsm']['value']:.2%}  | Meeting Rate: {m['nsm']['variants']['meeting_rate']['value']:.2%}")
    la = m["loss_attribution"]
    print(f"Потери: контекст {la['context_share']:.0%} / управляемое {la['controllable_share']:.0%}")
    print("\nБэклог (топ-3):")
    for h in backlog[:3]:
        print(f"  #{h['priority']} [{h['prompt_block']}] {h['hypothesis'][:70]}")
        print(f"     ΔNSM≈{h['expected_nsm_delta_pp']}pp · effort={h['effort']} · conf={h['confidence']}")
