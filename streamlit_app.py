from __future__ import annotations

import os
import tempfile

import pandas as pd
import streamlit as st

from entity_resolution import EntityResolver


st.set_page_config(
    page_title="Resolve — Entity Resolution Studio",
    page_icon="R",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');

    :root {
      --ink: #14231f;
      --muted: #6d7b75;
      --paper: #f7f8f4;
      --card: #ffffff;
      --line: #e3e8e1;
      --sage: #dce9df;
      --forest: #173f35;
      --lime: #c9f06b;
      --coral: #ff8a70;
      --violet: #7561e8;
    }

    html, body, [class*="css"] { font-family: 'Manrope', sans-serif; }
    .stApp { background: var(--paper); color: var(--ink); }
    .block-container { max-width: 1420px; padding: 2.1rem 3.5rem 4rem; }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stSidebar"] { background: #173f35; border-right: 0; }
    [data-testid="stSidebar"] * { color: #f5f7ed !important; }
    [data-testid="stSidebar"] .stSlider [data-baseweb="slider"] div { background: var(--lime); }
    [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.18); }
    [data-testid="stFileUploader"] section { background: #fbfcf9; border: 1px dashed #b9c8bd; border-radius: 16px; }
    [data-testid="stFileUploader"] section:hover { border-color: var(--forest); background: #f2f8ef; }
    [data-testid="stMetric"] { background: var(--card); border: 1px solid var(--line); padding: 1.05rem 1.15rem; border-radius: 16px; box-shadow: 0 8px 24px rgba(20,35,31,.04); }
    [data-testid="stMetricLabel"] { color: var(--muted); font-size: .75rem; text-transform: uppercase; letter-spacing: .10em; }
    [data-testid="stMetricValue"] { color: var(--ink); font-weight: 800; }
    .stButton > button { border-radius: 12px; border: 1px solid var(--forest); font-weight: 700; min-height: 2.8rem; }
    .stButton > button[kind="primary"] { background: var(--forest); color: white; border: 0; box-shadow: 0 8px 18px rgba(23,63,53,.18); }
    .stButton > button[kind="primary"]:hover { background: #0d3028; }
    .stDownloadButton > button { border-radius: 11px; font-weight: 700; }
    .stTabs [data-baseweb="tab-list"] { gap: 1.5rem; border-bottom: 1px solid var(--line); }
    .stTabs [data-baseweb="tab"] { padding: .85rem .1rem; font-weight: 700; color: var(--muted); }
    .stTabs [aria-selected="true"] { color: var(--forest); border-bottom-color: var(--forest); }
    .stDataFrame { border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }

    .topline { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.8rem; }
    .brand { display: flex; align-items: center; gap: .7rem; font-weight: 800; letter-spacing: -.03em; font-size: 1.05rem; }
    .brand-mark { width: 31px; height: 31px; display: grid; place-items: center; background: var(--lime); color: var(--forest); border-radius: 9px; font-family: 'DM Mono', monospace; font-weight: 500; }
    .status-pill { display: inline-flex; align-items: center; gap: .45rem; padding: .42rem .75rem; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); background: rgba(255,255,255,.68); font: 500 .72rem 'DM Mono', monospace; text-transform: uppercase; letter-spacing: .08em; }
    .status-dot { width: 7px; height: 7px; border-radius: 50%; background: #5aa469; }
    .hero { position: relative; overflow: hidden; background: var(--forest); border-radius: 26px; padding: 3rem 3.2rem 2.9rem; color: white; margin-bottom: 1.55rem; box-shadow: 0 18px 50px rgba(23,63,53,.18); }
    .hero:after { content: ''; position: absolute; width: 310px; height: 310px; border: 1px solid rgba(201,240,107,.22); border-radius: 50%; right: 7%; top: -180px; box-shadow: 0 0 0 36px rgba(201,240,107,.05), 0 0 0 72px rgba(201,240,107,.04); }
    .hero-kicker { position: relative; z-index: 1; color: var(--lime); font: 500 .72rem 'DM Mono', monospace; letter-spacing: .16em; text-transform: uppercase; margin-bottom: 1.2rem; }
    .hero h1 { position: relative; z-index: 1; color: white; font-size: clamp(2.35rem, 5vw, 4.4rem); line-height: .98; letter-spacing: -.075em; max-width: 760px; margin: 0 0 1.15rem; font-weight: 800; }
    .hero p { position: relative; z-index: 1; color: #d9e8de; max-width: 650px; font-size: 1.04rem; line-height: 1.65; margin: 0; }
    .hero-aside { position: absolute; z-index: 1; right: 3.2rem; bottom: 2.7rem; color: rgba(255,255,255,.66); font: 500 .72rem 'DM Mono', monospace; text-align: right; line-height: 1.7; }
    .section-label { color: var(--muted); font: 500 .71rem 'DM Mono', monospace; letter-spacing: .12em; text-transform: uppercase; margin: 1.6rem 0 .8rem; }
    .section-title { color: var(--ink); font-size: 1.65rem; font-weight: 800; letter-spacing: -.05em; margin: 0 0 .35rem; }
    .section-copy { color: var(--muted); font-size: .91rem; margin: 0 0 1.1rem; }
    .stepper { display: grid; grid-template-columns: repeat(4, 1fr); gap: .65rem; margin-bottom: 2rem; }
    .step { padding: .8rem .9rem; border: 1px solid var(--line); background: rgba(255,255,255,.55); border-radius: 13px; color: var(--muted); font-size: .77rem; font-weight: 700; }
    .step.active { border-color: #c6dc9c; background: #f0f7e8; color: var(--forest); }
    .step-num { display: inline-grid; place-items: center; width: 22px; height: 22px; margin-right: .38rem; border-radius: 7px; background: var(--sage); color: var(--forest); font: 500 .7rem 'DM Mono', monospace; }
    .step.active .step-num { background: var(--lime); }
    .upload-card { border: 1px solid var(--line); border-radius: 18px; padding: 1.3rem; background: var(--card); box-shadow: 0 8px 24px rgba(20,35,31,.035); }
    .upload-card-a { border-top: 4px solid var(--coral); }
    .upload-card-b { border-top: 4px solid var(--violet); }
    .upload-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: .65rem; }
    .upload-title { font-weight: 800; font-size: 1.05rem; letter-spacing: -.03em; }
    .upload-meta { color: var(--muted); font: 500 .68rem 'DM Mono', monospace; text-transform: uppercase; letter-spacing: .08em; }
    .file-chip { display: inline-block; margin-top: .65rem; padding: .35rem .55rem; border-radius: 7px; background: #f0f4ed; color: var(--forest); font: 500 .7rem 'DM Mono', monospace; }
    .control-caption { color: rgba(255,255,255,.62); font: 500 .68rem 'DM Mono', monospace; letter-spacing: .1em; text-transform: uppercase; margin: 1.2rem 0 .45rem; }
    .sidebar-brand { color: var(--lime); font: 500 .68rem 'DM Mono', monospace; letter-spacing: .14em; text-transform: uppercase; }
    .sidebar-title { color: white; font-size: 1.45rem; font-weight: 800; letter-spacing: -.05em; margin: .35rem 0 1.25rem; }
    .sidebar-help { color: rgba(255,255,255,.62); font-size: .76rem; line-height: 1.6; }
    .result-banner { display: flex; justify-content: space-between; align-items: center; gap: 1rem; padding: 1rem 1.2rem; border-radius: 15px; background: #eef7e8; border: 1px solid #d2e8ba; margin: 1.35rem 0 1rem; }
    .result-banner strong { color: var(--forest); }
    .result-banner span { color: #59715e; font-size: .8rem; }
    .mono { font-family: 'DM Mono', monospace; }
    @media (max-width: 900px) { .block-container { padding: 1.4rem 1rem 3rem; } .hero { padding: 2rem 1.5rem; } .hero-aside { display: none; } .stepper { grid-template-columns: repeat(2, 1fr); } }
    </style>
    """,
    unsafe_allow_html=True,
)


def read_preview(uploaded_file):
    if uploaded_file is None:
        return None
    uploaded_file.seek(0)
    return pd.read_csv(uploaded_file, dtype=str).fillna("")


def download_button(label, dataframe, filename):
    st.download_button(
        label,
        data=dataframe.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
        use_container_width=True,
    )


st.markdown(
    """
    <div class="topline">
      <div class="brand"><span class="brand-mark">R</span> resolve / studio</div>
      <div class="status-pill"><span class="status-dot"></span> local-first workspace</div>
    </div>
    <div class="hero">
      <div class="hero-kicker">Data quality · 01 / 03</div>
      <h1>Find the same person<br>in different data.</h1>
      <p>Turn messy customer exports into one trusted table. Resolve duplicates with transparent scoring, smart blocking, and a review queue built for human judgment.</p>
      <div class="hero-aside">NORMALIZE / COMPARE / MERGE<br>EXPLAINABLE BY DESIGN</div>
    </div>
    <div class="stepper">
      <div class="step active"><span class="step-num">01</span> Add sources</div>
      <div class="step"><span class="step-num">02</span> Tune matching</div>
      <div class="step"><span class="step-num">03</span> Review output</div>
      <div class="step"><span class="step-num">04</span> Export clean data</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown('<div class="sidebar-brand">resolve / controls</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-title">Tune the signal.</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-help">Shape how candidates are generated and how confidently the system labels them.</div>', unsafe_allow_html=True)
    st.markdown('<div class="control-caption">Candidate strategy</div>', unsafe_allow_html=True)
    blocking_strategy = st.selectbox(
        "Blocking strategy",
        options=["multi", "zip", "name_prefix", "soundex", "none"],
        index=0,
        label_visibility="collapsed",
        help="Controls how candidate pairs are generated before fuzzy comparison.",
    )
    st.markdown('<div class="control-caption">Decision thresholds</div>', unsafe_allow_html=True)
    match_threshold = st.slider(
        "Match threshold",
        min_value=0.0,
        max_value=1.0,
        value=0.70,
        step=0.01,
        help="Pairs at or above this score are treated as confirmed matches.",
    )
    review_threshold = st.slider(
        "Review threshold",
        min_value=0.0,
        max_value=1.0,
        value=0.50,
        step=0.01,
        help="Pairs between this score and the match threshold are sent to review.",
    )
    if review_threshold > match_threshold:
        st.warning("Review must be below match.")
    st.divider()
    st.markdown('<div class="control-caption">Expected schema</div>', unsafe_allow_html=True)
    st.code("id, first_name, last_name,\nemail, phone, address, city,\nstate, zip", language="text")
    st.markdown('<div class="sidebar-help">Your files stay in memory during the run and are not persisted by this app.</div>', unsafe_allow_html=True)

st.markdown('<div class="section-label">01 / Input workspace</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">Bring the two versions together.</div>', unsafe_allow_html=True)
st.markdown('<div class="section-copy">Upload clean or imperfect CSV exports. We will preview them before running any comparisons.</div>', unsafe_allow_html=True)

col_a, col_b = st.columns(2, gap="large")
with col_a:
    st.markdown('<div class="upload-card upload-card-a"><div class="upload-head"><span class="upload-title">Source A</span><span class="upload-meta">primary</span></div>', unsafe_allow_html=True)
    file_a = st.file_uploader("Upload the first customer CSV", type=["csv"], key="source_a", label_visibility="collapsed")
    if file_a is not None:
        st.markdown(f'<span class="file-chip">{file_a.name}</span>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
with col_b:
    st.markdown('<div class="upload-card upload-card-b"><div class="upload-head"><span class="upload-title">Source B</span><span class="upload-meta">enrichment</span></div>', unsafe_allow_html=True)
    file_b = st.file_uploader("Upload the second customer CSV", type=["csv"], key="source_b", label_visibility="collapsed")
    if file_b is not None:
        st.markdown(f'<span class="file-chip">{file_b.name}</span>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

if file_a is not None or file_b is not None:
    st.markdown('<div class="section-label">Preview</div>', unsafe_allow_html=True)
    preview_a, preview_b = st.columns(2, gap="large")
    for uploaded, container in ((file_a, preview_a), (file_b, preview_b)):
        if uploaded is None:
            continue
        try:
            preview = read_preview(uploaded)
            with container:
                st.caption(f"{uploaded.name}  /  {len(preview):,} records  /  {len(preview.columns)} columns")
                st.dataframe(preview.head(4), use_container_width=True, hide_index=True)
        except Exception as exc:
            with container:
                st.error(f"Could not read {uploaded.name}: {exc}")

ready = file_a is not None and file_b is not None and review_threshold <= match_threshold
st.markdown("<br>", unsafe_allow_html=True)
run_clicked = st.button("Run resolution  →", type="primary", use_container_width=True, disabled=not ready)
if not ready and (file_a is not None or file_b is not None):
    st.caption("Add both CSV files and keep the review threshold below the match threshold to continue.")

if run_clicked:
    temp_paths: list[str] = []
    try:
        with tempfile.NamedTemporaryFile(mode="wb", suffix="_source_a.csv", delete=False) as tmp_a:
            tmp_a.write(file_a.getvalue())
            path_a = tmp_a.name
            temp_paths.append(path_a)
        with tempfile.NamedTemporaryFile(mode="wb", suffix="_source_b.csv", delete=False) as tmp_b:
            tmp_b.write(file_b.getvalue())
            path_b = tmp_b.name
            temp_paths.append(path_b)

        with st.spinner("Working through the matching graph…"):
            resolver = EntityResolver(
                path_a=path_a,
                path_b=path_b,
                match_threshold=match_threshold,
                review_threshold=review_threshold,
                blocking_strategy=blocking_strategy,
                verbose=False,
            )
            results = resolver.run()

        st.session_state["resolution_results"] = results
        st.session_state["resolution_settings"] = {
            "source_a": file_a.name,
            "source_b": file_b.name,
            "blocking_strategy": blocking_strategy,
            "match_threshold": match_threshold,
            "review_threshold": review_threshold,
        }
        st.success("Resolution complete. Your workspace is ready below.")
    except Exception as exc:
        st.exception(exc)
    finally:
        for temp_path in temp_paths:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

if "resolution_results" in st.session_state:
    results = st.session_state["resolution_results"]
    settings = st.session_state["resolution_settings"]
    stats = results["stats"]

    st.markdown('<div class="section-label">02 / Results workspace</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">A clearer view of what changed.</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-copy">Every result remains traceable: confirmed matches, ambiguous candidates, and records unique to either source.</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="result-banner"><div><strong>Resolution finished</strong><br><span>{settings["source_a"]} + {settings["source_b"]}</span></div><span class="mono">{settings["blocking_strategy"]} / {settings["match_threshold"]:.2f} match / {settings["review_threshold"]:.2f} review</span></div>',
        unsafe_allow_html=True,
    )

    metrics = st.columns(5, gap="small")
    metrics[0].metric("Confirmed matches", f"{stats.get('best_dedup_matches', 0):,}")
    metrics[1].metric("Needs review", f"{stats.get('review', 0):,}")
    metrics[2].metric("Merged records", f"{stats.get('merged_records', 0):,}")
    metrics[3].metric("Search reduction", f"{stats.get('block_reduction', 0):.1%}")
    metrics[4].metric("Pairs compared", f"{stats.get('pairs_compared', 0):,}")

    st.markdown("<br>", unsafe_allow_html=True)
    tab_merged, tab_review, tab_comparisons, tab_stats = st.tabs(
        ["Merged output", "Review queue", "All comparisons", "Run diagnostics"]
    )

    with tab_merged:
        merged = results["merged"]
        st.caption(f"{len(merged):,} records in the final unified table")
        st.dataframe(merged, use_container_width=True, hide_index=True)
        download_button("Download merged output", merged, "merged_output.csv")

    with tab_review:
        review = results["review"]
        if review.empty:
            st.success("No candidate pairs require manual review. The thresholds produced a decisive run.")
        else:
            st.caption(f"{len(review):,} pairs fall into the review band")
            st.dataframe(review.sort_values("overall_score", ascending=False), use_container_width=True, hide_index=True)
            download_button("Download review queue", review, "review_queue.csv")

    with tab_comparisons:
        comparisons = results["comparisons"]
        st.caption(f"{len(comparisons):,} candidate pairs with field-level scores")
        st.dataframe(comparisons, use_container_width=True, hide_index=True)
        download_button("Download all comparisons", comparisons, "all_comparisons.csv")

    with tab_stats:
        left, right = st.columns([1.2, .8], gap="large")
        with left:
            st.markdown("#### Run profile")
            profile = pd.DataFrame(
                {
                    "Measure": ["Blocks created", "Naive pairs", "Candidate pairs", "Comparison time", "Unique to source A", "Unique to source B"],
                    "Value": [
                        f"{stats.get('blocks', 0):,}",
                        f"{stats.get('naive_pairs', 0):,}",
                        f"{stats.get('candidate_pairs', 0):,}",
                        f"{stats.get('comparison_time_s', 0):.3f}s",
                        f"{stats.get('unique_to_a', 0):,}",
                        f"{stats.get('unique_to_b', 0):,}",
                    ],
                }
            )
            st.dataframe(profile, use_container_width=True, hide_index=True)
        with right:
            st.markdown("#### Decision mix")
            decision_mix = pd.DataFrame(
                {"Decision": ["Match", "Review", "Non-match"], "Pairs": [stats.get("matches", 0), stats.get("review", 0), stats.get("non_match", 0)]}
            ).set_index("Decision")
            st.bar_chart(decision_mix, color="#7561e8")
