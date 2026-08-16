from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from entity_resolution import EntityResolver


st.set_page_config(
    page_title="Entity Resolution Studio",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 2.4rem; padding-bottom: 3rem; }
    .hero { padding: 1.4rem 1.6rem; border-radius: 1rem; background: linear-gradient(135deg, #102a43 0%, #1f4e79 60%, #2f80ed 100%); color: white; margin-bottom: 1.2rem; }
    .hero h1 { color: white; margin-bottom: 0.35rem; }
    .hero p { color: #e8f1fb; font-size: 1.05rem; margin-bottom: 0; }
    .small-note { color: #52606d; font-size: 0.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>Entity Resolution Studio</h1>
      <p>Upload two customer datasets, resolve likely duplicates, inspect decisions, and download clean outputs.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Matching controls")
    blocking_strategy = st.selectbox(
        "Blocking strategy",
        options=["multi", "zip", "name_prefix", "soundex", "none"],
        index=0,
        help="Controls how candidate pairs are generated before fuzzy comparison.",
    )
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
        st.warning("The review threshold should not exceed the match threshold.")
    st.divider()
    st.markdown("**Expected columns**")
    st.code("id, first_name, last_name, email, phone, address, city, state, zip", language="text")
    st.markdown('<p class="small-note">Input files are processed in memory and are not persisted by this app.</p>', unsafe_allow_html=True)

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Source A")
    file_a = st.file_uploader("Upload the first customer CSV", type=["csv"], key="source_a")
with col_b:
    st.subheader("Source B")
    file_b = st.file_uploader("Upload the second customer CSV", type=["csv"], key="source_b")

if file_a is not None or file_b is not None:
    preview_a, preview_b = st.columns(2)
    if file_a is not None:
        try:
            df_a_preview = pd.read_csv(file_a, dtype=str).fillna("")
            with preview_a:
                st.caption(f"{file_a.name} · {len(df_a_preview):,} records")
                st.dataframe(df_a_preview.head(5), use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"Could not read Source A: {exc}")
    if file_b is not None:
        try:
            df_b_preview = pd.read_csv(file_b, dtype=str).fillna("")
            with preview_b:
                st.caption(f"{file_b.name} · {len(df_b_preview):,} records")
                st.dataframe(df_b_preview.head(5), use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"Could not read Source B: {exc}")

run_clicked = st.button("Run entity resolution", type="primary", use_container_width=True, disabled=file_a is None or file_b is None)

if run_clicked:
    if review_threshold > match_threshold:
        st.error("Please set the review threshold at or below the match threshold.")
        st.stop()

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

        with st.spinner("Normalizing, blocking, comparing, and merging records…"):
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
        st.success("Entity resolution completed successfully.")
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

    st.divider()
    st.subheader("Resolution summary")
    metrics = st.columns(5)
    metrics[0].metric("Confirmed matches", f"{stats.get('best_dedup_matches', 0):,}")
    metrics[1].metric("Review candidates", f"{stats.get('review', 0):,}")
    metrics[2].metric("Merged records", f"{stats.get('merged_records', 0):,}")
    metrics[3].metric("Candidate reduction", f"{stats.get('block_reduction', 0):.1%}")
    metrics[4].metric("Pairs compared", f"{stats.get('pairs_compared', 0):,}")

    st.caption(
        f"{settings['source_a']} + {settings['source_b']} · "
        f"blocking: `{settings['blocking_strategy']}` · "
        f"thresholds: match `{settings['match_threshold']:.2f}`, review `{settings['review_threshold']:.2f}`"
    )

    tab_merged, tab_review, tab_comparisons, tab_stats = st.tabs(
        ["Merged output", "Review queue", "All comparisons", "Diagnostics"]
    )

    with tab_merged:
        merged = results["merged"]
        st.dataframe(merged, use_container_width=True, hide_index=True)
        st.download_button(
            "Download merged_output.csv",
            data=merged.to_csv(index=False).encode("utf-8"),
            file_name="merged_output.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with tab_review:
        review = results["review"]
        if review.empty:
            st.success("No candidate pairs require manual review.")
        else:
            st.dataframe(review.sort_values("overall_score", ascending=False), use_container_width=True, hide_index=True)
            st.download_button(
                "Download review_queue.csv",
                data=review.to_csv(index=False).encode("utf-8"),
                file_name="review_queue.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with tab_comparisons:
        comparisons = results["comparisons"]
        st.dataframe(comparisons, use_container_width=True, hide_index=True)
        st.download_button(
            "Download all_comparisons.csv",
            data=comparisons.to_csv(index=False).encode("utf-8"),
            file_name="all_comparisons.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with tab_stats:
        st.json(stats)
