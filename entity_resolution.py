""""
Customer Record Entity Resolution System
==========================================
Implements fuzzy matching (Levenshtein, Jaro-Winkler) to identify
duplicate customer records across two datasets.

Features:
  - Fuzzy matching via RapidFuzz (or difflib fallback)
  - Blocking strategies to scale to large tables
  - Conflict resolution and merge logic
  - Match statistics report

Usage:
    python entity_resolution.py

Or import as a module:
    from entity_resolution import EntityResolver
    resolver = EntityResolver("customers_a.csv", "customers_b.csv")
    results = resolver.run()
"""

import pandas as pd  # type: ignore
import numpy as np  # type: ignore
import re
import time
from datetime import datetime
from collections import defaultdict

# ── Fuzzy matching backend ────────────────────────────────────────────────────
try:
    from rapidfuzz import fuzz as rfuzz  # type: ignore
    from rapidfuzz.distance import Levenshtein as rLevenshtein  # type: ignore
    from rapidfuzz.distance import JaroWinkler as rJaroWinkler  # type: ignore

    def levenshtein_similarity(a: str, b: str) -> float:
        """Return Levenshtein similarity score in [0, 1]."""
        return rfuzz.ratio(a, b) / 100.0

    def jaro_winkler_similarity(a: str, b: str) -> float:
        """Return Jaro-Winkler similarity score in [0, 1]."""
        return rJaroWinkler.normalized_similarity(a, b)

    def token_sort_similarity(a: str, b: str) -> float:
        return rfuzz.token_sort_ratio(a, b) / 100.0

    BACKEND = "rapidfuzz"

except ImportError:
    # Pure-Python fallback using difflib
    import difflib
    import math

    def _jaro(s1: str, s2: str) -> float:
        """Jaro similarity (pure Python)."""
        if s1 == s2:
            return 1.0
        len1, len2 = len(s1), len(s2)
        if len1 == 0 or len2 == 0:
            return 0.0
        match_dist = max(len1, len2) // 2 - 1
        s1_matches = [False] * len1
        s2_matches = [False] * len2
        matches = 0
        transpositions = 0
        for i in range(len1):
            start = max(0, i - match_dist)
            end = min(i + match_dist + 1, len2)
            for j in range(start, end):
                if s2_matches[j] or s1[i] != s2[j]:
                    continue
                s1_matches[i] = s2_matches[j] = True
                matches += 1
                break
        if matches == 0:
            return 0.0
        k = 0
        for i in range(len1):
            if not s1_matches[i]:
                continue
            while not s2_matches[k]:
                k += 1
            if s1[i] != s2[k]:
                transpositions += 1
            k += 1
        return (matches / len1 + matches / len2 +
                (matches - transpositions / 2) / matches) / 3

    def jaro_winkler_similarity(a: str, b: str, p: float = 0.1) -> float:
        jaro = _jaro(a, b)
        prefix = 0
        for c1, c2 in zip(a[:4], b[:4]):
            if c1 == c2:
                prefix += 1
            else:
                break
        return jaro + prefix * p * (1 - jaro)

    def levenshtein_similarity(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio()

    def token_sort_similarity(a: str, b: str) -> float:
        a_tokens = " ".join(sorted(a.lower().split()))
        b_tokens = " ".join(sorted(b.lower().split()))
        return levenshtein_similarity(a_tokens, b_tokens)

    BACKEND = "difflib"

print(f"[INFO] Fuzzy backend: {BACKEND}")


# ── Text normalisation helpers ────────────────────────────────────────────────

def normalize_phone(phone: str) -> str:
    """Strip non-digit characters, keep last 10 digits."""
    if pd.isna(phone) or str(phone).strip() == "":
        return ""
    return re.sub(r"\D", "", str(phone))[-10:]

def normalize_name(name: str) -> str:
    """Lowercase, strip accents, remove punctuation."""
    if pd.isna(name) or str(name).strip() == "":
        return ""
    return re.sub(r"[^a-z\s]", "", str(name).lower().strip())

def normalize_address(addr: str) -> str:
    """Expand common abbreviations, lowercase."""
    if pd.isna(addr) or str(addr).strip() == "":
        return ""
    addr = str(addr).lower().strip()
    addr = re.sub(r"[^\w\s]", " ", addr)
    abbreviations = {
        r"\bst\b": "street", r"\bave?\b": "avenue", r"\bblvd\b": "boulevard",
        r"\brd\b": "road",   r"\bdr\b": "drive",   r"\bct\b": "court",
        r"\bln\b": "lane",   r"\bpl\b": "place",   r"\bsq\b": "square",
        r"\bfw?y\b": "freeway",
    }
    for pattern, replacement in abbreviations.items():
        addr = re.sub(pattern, replacement, addr)
    return re.sub(r"\s+", " ", addr).strip()

def normalize_email(email: str) -> str:
    if pd.isna(email) or str(email).strip() == "":
        return ""
    return str(email).lower().strip()

def normalize_zip(z: str) -> str:
    if pd.isna(z):
        return ""
    return str(z).strip()[:5]


# ── Blocking strategies ───────────────────────────────────────────────────────

class BlockingStrategy:
    """
    Blocking reduces the O(n²) candidate space.
    Only pairs sharing a block key are compared.
    """

    @staticmethod
    def zip_block(df: pd.DataFrame) -> pd.Series:
        """Block on 5-digit ZIP code."""
        return df["zip"].apply(normalize_zip)

    @staticmethod
    def name_prefix_block(df: pd.DataFrame) -> pd.Series:
        """Block on first 3 chars of last_name (case-insensitive)."""
        return df["last_name"].apply(
            lambda x: normalize_name(x)[:3] if not pd.isna(x) else "___"
        )

    @staticmethod
    def phone_prefix_block(df: pd.DataFrame) -> pd.Series:
        """Block on first 6 digits of normalized phone."""
        return df["phone"].apply(lambda x: normalize_phone(x)[:6])

    @staticmethod
    def soundex_block(df: pd.DataFrame) -> pd.Series:
        """Soundex of last_name — catches phonetic duplicates."""
        def soundex(name: str) -> str:
            name = normalize_name(name).upper().replace(" ", "")
            if not name:
                return "0000"
            mapping = {
                'B': '1', 'F': '1', 'P': '1', 'V': '1',
                'C': '2', 'G': '2', 'J': '2', 'K': '2',
                'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
                'D': '3', 'T': '3', 'L': '4',
                'M': '5', 'N': '5', 'R': '6',
            }
            code = name[0]
            prev = mapping.get(name[0], '0')
            for ch in name[1:]:
                c = mapping.get(ch, '0')
                if c != '0' and c != prev:
                    code += c
                prev = c
            return (code + "000")[:4]

        return df["last_name"].apply(soundex)

    @staticmethod
    def multi_block(df: pd.DataFrame) -> pd.Series:
        """Composite block: ZIP + soundex(last_name)."""
        z = BlockingStrategy.zip_block(df)
        s = BlockingStrategy.soundex_block(df)
        return z + "|" + s


# ── Scoring engine ────────────────────────────────────────────────────────────

class FieldWeights:
    """
    Weights for individual field comparison scores.
    Adjust to tune precision vs recall for your domain.
    """
    name_first     = 0.15
    name_last      = 0.25
    email          = 0.20
    phone          = 0.20
    address        = 0.10
    city           = 0.05
    state          = 0.03
    zip_code       = 0.02


def compare_records(row_a: pd.Series, row_b: pd.Series) -> dict:
    """
    Compare two customer records and return a scored comparison dict.
    Each field is scored in [0, 1]; the weighted sum is the overall score.
    """
    scores = {}

    # ── Name comparison (use Jaro-Winkler — better for name typos) ─────────
    fn_a = normalize_name(str(row_a.get("first_name", "")))
    fn_b = normalize_name(str(row_b.get("first_name", "")))
    ln_a = normalize_name(str(row_a.get("last_name", "")))
    ln_b = normalize_name(str(row_b.get("last_name", "")))

    scores["first_name"] = jaro_winkler_similarity(fn_a, fn_b) if fn_a and fn_b else 0.0
    scores["last_name"]  = jaro_winkler_similarity(ln_a, ln_b) if ln_a and ln_b else 0.0

    # Also try swapped first/last in case data was mis-entered
    swapped = jaro_winkler_similarity(fn_a, ln_b) * jaro_winkler_similarity(ln_a, fn_b)
    if swapped > scores["first_name"] * scores["last_name"]:
        scores["first_name"] = jaro_winkler_similarity(fn_a, ln_b)
        scores["last_name"]  = jaro_winkler_similarity(ln_a, fn_b)
        scores["_name_swapped"] = True

    # ── Email ────────────────────────────────────────────────────────────────
    em_a = normalize_email(str(row_a.get("email", "")))
    em_b = normalize_email(str(row_b.get("email", "")))
    if em_a and em_b:
        if em_a == em_b:
            scores["email"] = 1.0
        else:
            # Exact match on local part (before @)
            local_a = em_a.split("@")[0] if "@" in em_a else em_a
            local_b = em_b.split("@")[0] if "@" in em_b else em_b
            scores["email"] = max(
                levenshtein_similarity(em_a, em_b),
                0.8 * token_sort_similarity(local_a, local_b)
            )
    else:
        scores["email"] = 0.0

    # ── Phone ────────────────────────────────────────────────────────────────
    ph_a = normalize_phone(str(row_a.get("phone", "")))
    ph_b = normalize_phone(str(row_b.get("phone", "")))
    if ph_a and ph_b and len(ph_a) >= 7 and len(ph_b) >= 7:
        if ph_a == ph_b:
            scores["phone"] = 1.0
        elif ph_a[-7:] == ph_b[-7:]:
            scores["phone"] = 0.9   # same local number, different area code
        else:
            scores["phone"] = levenshtein_similarity(ph_a, ph_b) * 0.7
    else:
        scores["phone"] = 0.0

    # ── Address ──────────────────────────────────────────────────────────────
    ad_a = normalize_address(str(row_a.get("address", "")))
    ad_b = normalize_address(str(row_b.get("address", "")))
    if ad_a and ad_b:
        scores["address"] = token_sort_similarity(ad_a, ad_b)
    else:
        scores["address"] = 0.0

    # ── City ─────────────────────────────────────────────────────────────────
    ci_a = normalize_name(str(row_a.get("city", "")))
    ci_b = normalize_name(str(row_b.get("city", "")))
    scores["city"] = jaro_winkler_similarity(ci_a, ci_b) if ci_a and ci_b else 0.0

    # ── State ────────────────────────────────────────────────────────────────
    st_a = str(row_a.get("state", "")).upper().strip()
    st_b = str(row_b.get("state", "")).upper().strip()
    scores["state"] = 1.0 if st_a == st_b and st_a != "" else 0.0

    # ── ZIP ──────────────────────────────────────────────────────────────────
    z_a = normalize_zip(str(row_a.get("zip", "")))
    z_b = normalize_zip(str(row_b.get("zip", "")))
    if z_a and z_b:
        scores["zip"] = 1.0 if z_a == z_b else levenshtein_similarity(z_a, z_b)
    else:
        scores["zip"] = 0.0

    # ── Weighted overall score ───────────────────────────────────────────────
    w = FieldWeights
    overall = (
        scores["first_name"] * w.name_first +
        scores["last_name"]  * w.name_last  +
        scores["email"]      * w.email      +
        scores["phone"]      * w.phone      +
        scores["address"]    * w.address    +
        scores["city"]       * w.city       +
        scores["state"]      * w.state      +
        scores["zip"]        * w.zip_code
    )

    scores["overall_score"] = round(overall, 4)
    return scores


# ── Conflict resolution ───────────────────────────────────────────────────────

class ConflictResolver:
    """
    Given two matching records A and B, produce a single merged record.
    Strategy: prefer the non-null, longer, or more recently normalised value.
    """

    FIELD_PRIORITY = {
        # field: prefer source 'a', 'b', or 'longer' / 'non_null'
        "first_name": "longer",
        "last_name":  "longer",
        "email":      "non_null",
        "phone":      "non_null",
        "address":    "longer",
        "city":       "non_null",
        "state":      "non_null",
        "zip":        "non_null",
    }

    @classmethod
    def merge(cls, row_a: pd.Series, row_b: pd.Series,
              scores: dict) -> pd.Series:
        """Return merged record with provenance annotations."""
        merged = {}

        for field, strategy in cls.FIELD_PRIORITY.items():
            val_a = row_a.get(field, "")
            val_b = row_b.get(field, "")
            na_a  = pd.isna(val_a) or str(val_a).strip() == ""
            na_b  = pd.isna(val_b) or str(val_b).strip() == ""

            if na_a and na_b:
                merged[field] = ""
            elif na_a:
                merged[field] = val_b
            elif na_b:
                merged[field] = val_a
            elif strategy == "longer":
                merged[field] = val_a if len(str(val_a)) >= len(str(val_b)) else val_b
            else:
                merged[field] = val_a   # default: prefer source A

        merged["source_id_a"]    = row_a.get("id", "")
        merged["source_id_b"]    = row_b.get("id", "")
        merged["match_score"]    = scores["overall_score"]
        merged["merge_decision"] = "matched"
        return pd.Series(merged)


# ── Main resolver ─────────────────────────────────────────────────────────────

class EntityResolver:
    """
    End-to-end customer record entity resolution pipeline.

    Parameters
    ----------
    path_a, path_b      : CSV file paths
    match_threshold     : minimum overall score to consider a match   (default 0.75)
    review_threshold    : score below this is flagged for manual review (default 0.55)
    blocking_strategy   : 'multi' | 'zip' | 'name_prefix' | 'soundex' | 'none'
    verbose             : print progress messages
    """

    def __init__(
        self,
        path_a: str,
        path_b: str,
        match_threshold: float   = 0.75,
        review_threshold: float  = 0.55,
        blocking_strategy: str   = "multi",
        verbose: bool            = True,
    ):
        self.path_a            = path_a
        self.path_b            = path_b
        self.match_threshold   = match_threshold
        self.review_threshold  = review_threshold
        self.blocking_strategy = blocking_strategy
        self.verbose           = verbose

        self.df_a: pd.DataFrame = None
        self.df_b: pd.DataFrame = None
        self.candidates: list   = []
        self.results: pd.DataFrame = None
        self.stats: dict        = {}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, msg):
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def _load(self):
        self._log(f"Loading {self.path_a} …")
        self.df_a = pd.read_csv(self.path_a, dtype=str).fillna("")
        self._log(f"  → {len(self.df_a)} records")
        self._log(f"Loading {self.path_b} …")
        self.df_b = pd.read_csv(self.path_b, dtype=str).fillna("")
        self._log(f"  → {len(self.df_b)} records")

    def _build_blocks(self) -> dict:
        """
        Return a dict: block_key → {"a": [idx…], "b": [idx…]}
        """
        strat_map = {
            "multi":       BlockingStrategy.multi_block,
            "zip":         BlockingStrategy.zip_block,
            "name_prefix": BlockingStrategy.name_prefix_block,
            "soundex":     BlockingStrategy.soundex_block,
        }

        if self.blocking_strategy == "none":
            return {"ALL": {
                "a": list(self.df_a.index),
                "b": list(self.df_b.index),
            }}

        fn = strat_map[self.blocking_strategy]
        blocks: dict = defaultdict(lambda: {"a": [], "b": []})
        for idx, row in self.df_a.iterrows():
            key = fn(self.df_a.loc[[idx]])[idx]
            blocks[key]["a"].append(idx)
        for idx, row in self.df_b.iterrows():
            key = fn(self.df_b.loc[[idx]])[idx]
            blocks[key]["b"].append(idx)
        return dict(blocks)

    # ── Pipeline stages ───────────────────────────────────────────────────────

    def stage_block(self):
        self._log(f"Building blocks (strategy='{self.blocking_strategy}') …")
        blocks = self._build_blocks()
        total_pairs = sum(
            len(v["a"]) * len(v["b"]) for v in blocks.values()
        )
        naive_pairs = len(self.df_a) * len(self.df_b)
        reduction   = 1 - total_pairs / naive_pairs if naive_pairs else 0
        self._log(
            f"  → {len(blocks)} blocks | "
            f"{total_pairs:,} candidate pairs "
            f"(vs {naive_pairs:,} naive, {reduction:.1%} reduction)"
        )
        self.stats["blocks"]          = len(blocks)
        self.stats["candidate_pairs"] = total_pairs
        self.stats["naive_pairs"]     = naive_pairs
        self.stats["block_reduction"] = reduction
        return blocks

    def stage_compare(self, blocks: dict):
        self._log("Comparing candidate pairs …")
        t0 = time.time()
        rows = []
        compared = 0

        for bk, members in blocks.items():
            for ia in members["a"]:
                for ib in members["b"]:
                    row_a = self.df_a.loc[ia]
                    row_b = self.df_b.loc[ib]
                    scores = compare_records(row_a, row_b)
                    rows.append({
                        "idx_a":   ia,
                        "idx_b":   ib,
                        "block":   bk,
                        **scores,
                    })
                    compared += 1

        elapsed = time.time() - t0
        self._log(f"  → {compared:,} pairs in {elapsed:.2f}s "
                  f"({compared/max(elapsed,1e-9):,.0f} pairs/s)")
        self.stats["pairs_compared"] = compared
        self.stats["comparison_time_s"] = round(elapsed, 3)
        return pd.DataFrame(rows)

    def stage_classify(self, comparisons: pd.DataFrame) -> pd.DataFrame:
        """Classify each pair as match / review / non-match."""
        self._log("Classifying pairs …")
        comparisons = comparisons.copy()

        def classify(score):
            if score >= self.match_threshold:
                return "match"
            elif score >= self.review_threshold:
                return "review"
            return "non-match"

        comparisons["decision"] = comparisons["overall_score"].apply(classify)

        # De-duplicate: keep best match per record in B
        matches = comparisons[comparisons["decision"] == "match"]
        best_matches = (
            matches.sort_values("overall_score", ascending=False)
                   .drop_duplicates(subset=["idx_b"])
                   .drop_duplicates(subset=["idx_a"])
        )
        review = comparisons[comparisons["decision"] == "review"]

        counts = comparisons["decision"].value_counts().to_dict()
        self._log(
            f"  → matches: {counts.get('match',0)} | "
            f"review: {counts.get('review',0)} | "
            f"non-match: {counts.get('non-match',0)}"
        )
        self.stats.update({
            "matches":    counts.get("match", 0),
            "review":     counts.get("review", 0),
            "non_match":  counts.get("non-match", 0),
            "best_dedup_matches": len(best_matches),
        })
        return comparisons, best_matches, review

    def stage_merge(self, best_matches: pd.DataFrame) -> pd.DataFrame:
        """Merge matched pairs into unified records."""
        self._log("Merging matched records …")
        merged_rows = []

        matched_a_ids = set()
        matched_b_ids = set()

        for _, match in best_matches.iterrows():
            ia, ib = int(match["idx_a"]), int(match["idx_b"])
            row_a  = self.df_a.loc[ia]
            row_b  = self.df_b.loc[ib]
            scores = {k: match[k] for k in match.index}
            merged = ConflictResolver.merge(row_a, row_b, scores)
            merged_rows.append(merged)
            matched_a_ids.add(ia)
            matched_b_ids.add(ib)

        # Un-matched records from A (unique to A)
        for ia in self.df_a.index:
            if ia not in matched_a_ids:
                row = self.df_a.loc[ia].copy()
                row["source_id_a"]    = row.get("id", "")
                row["source_id_b"]    = ""
                row["match_score"]    = 0.0
                row["merge_decision"] = "unique_a"
                merged_rows.append(row)

        # Un-matched records from B (unique to B)
        for ib in self.df_b.index:
            if ib not in matched_b_ids:
                row = self.df_b.loc[ib].copy()
                row["source_id_a"]    = ""
                row["source_id_b"]    = row.get("id", "")
                row["match_score"]    = 0.0
                row["merge_decision"] = "unique_b"
                merged_rows.append(row)

        merged_df = pd.DataFrame(merged_rows).reset_index(drop=True)

        self._log(f"  → merged output: {len(merged_df)} records")
        self.stats["merged_records"]  = len(merged_df)
        self.stats["unique_to_a"]     = sum(1 for r in merged_rows
                                            if r.get("merge_decision") == "unique_a")
        self.stats["unique_to_b"]     = sum(1 for r in merged_rows
                                            if r.get("merge_decision") == "unique_b")
        return merged_df

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self) -> dict:
        """
        Execute the full entity resolution pipeline.
        Returns a dict with keys:
          - merged       : pd.DataFrame  (final merged table)
          - comparisons  : pd.DataFrame  (all pair scores)
          - review       : pd.DataFrame  (pairs flagged for manual review)
          - stats        : dict          (summary statistics)
        """
        self._load()
        blocks      = self.stage_block()
        comparisons = self.stage_compare(blocks)
        comparisons, best_matches, review = self.stage_classify(comparisons)
        merged      = self.stage_merge(best_matches)

        self.results = {
            "merged":      merged,
            "comparisons": comparisons,
            "review":      review,
            "stats":       self.stats,
        }
        return self.results

    def save_outputs(self, output_dir: str = "."):
        """Save all outputs to CSV files."""
        import os
        os.makedirs(output_dir, exist_ok=True)
        r = self.results
        r["merged"].to_csv(f"{output_dir}/merged_output.csv", index=False)
        r["comparisons"].to_csv(f"{output_dir}/all_comparisons.csv", index=False)
        r["review"].to_csv(f"{output_dir}/review_queue.csv", index=False)
        self._log(f"Outputs saved to '{output_dir}/'")

    def print_report(self):
        """Print a formatted summary report."""
        s = self.stats
        sep = "─" * 58
        print(f"\n{'═'*58}")
        print(f"  CUSTOMER ENTITY RESOLUTION — MATCH REPORT")
        print(f"{'═'*58}")
        print(f"\n  INPUT")
        print(f"  {'Source A records:':<30} {len(self.df_a):>8,}")
        print(f"  {'Source B records:':<30} {len(self.df_b):>8,}")

        print(f"\n  BLOCKING  (strategy: {self.blocking_strategy})")
        print(f"  {'Blocks created:':<30} {s.get('blocks',0):>8,}")
        print(f"  {'Naive pair comparisons:':<30} {s.get('naive_pairs',0):>8,}")
        print(f"  {'Candidate pairs (post-block):':<30} {s.get('candidate_pairs',0):>8,}")
        print(f"  {'Reduction:':<30} {s.get('block_reduction',0):>8.1%}")

        print(f"\n  MATCHING")
        print(f"  {'Pairs compared:':<30} {s.get('pairs_compared',0):>8,}")
        print(f"  {'Confirmed matches:':<30} {s.get('best_dedup_matches',0):>8,}")
        print(f"  {'Flagged for review:':<30} {s.get('review',0):>8,}")

        print(f"\n  MERGED OUTPUT")
        print(f"  {'Merged (de-duplicated) records:':<30} {s.get('merged_records',0):>8,}")
        print(f"  {'Unique to source A:':<30} {s.get('unique_to_a',0):>8,}")
        print(f"  {'Unique to source B:':<30} {s.get('unique_to_b',0):>8,}")
        print(f"  {'Matched pairs merged:':<30} {s.get('best_dedup_matches',0):>8,}")
        print(f"\n  PERFORMANCE")
        print(f"  {'Comparison time:':<30} {s.get('comparison_time_s',0):>8.3f}s")
        print(f"{'═'*58}\n")


# ── Sample run ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    resolver = EntityResolver(
        path_a            = os.path.join(script_dir, "customers_a.csv"),
        path_b            = os.path.join(script_dir, "customers_b.csv"),
        match_threshold   = 0.70,
        review_threshold  = 0.50,
        blocking_strategy = "multi",
        verbose           = True,
    )

    results = resolver.run()
    resolver.print_report()
    resolver.save_outputs(output_dir="output")

    # ── Show sample matches ───────────────────────────────────────────────────
    print("\n  TOP MATCHES (score ≥ threshold):")
    print("  " + "─" * 78)
    matches_df = results["comparisons"][results["comparisons"]["decision"] == "match"]
    matches_df = matches_df.sort_values("overall_score", ascending=False)
    for _, row in matches_df.head(10).iterrows():
        a = resolver.df_a.loc[int(row["idx_a"])]
        b = resolver.df_b.loc[int(row["idx_b"])]
        print(f"  Score {row['overall_score']:.3f}  |  "
              f"A: {a['first_name']} {a['last_name']} ({a['email']})  ↔  "
              f"B: {b['first_name']} {b['last_name']} ({b['email']})")

    # ── Show review queue ─────────────────────────────────────────────────────
    if len(results["review"]) > 0:
        print(f"\n  REVIEW QUEUE ({len(results['review'])} pairs):")
        print("  " + "─" * 78)
        for _, row in results["review"].sort_values("overall_score", ascending=False).head(5).iterrows():
            a = resolver.df_a.loc[int(row["idx_a"])]
            b = resolver.df_b.loc[int(row["idx_b"])]
            print(f"  Score {row['overall_score']:.3f}  |  "
                  f"A: {a['first_name']} {a['last_name']}  ↔  "
                  f"B: {b['first_name']} {b['last_name']}  "
                  f"[last_name:{row.get('last_name', 0):.2f} email:{row.get('email', 0):.2f} phone:{row.get('phone', 0):.2f}]")

    print("\n  ✓ Outputs written to ./output/")
    print("    • merged_output.csv    — de-duplicated master table")
    print("    • all_comparisons.csv  — all pair scores")
    print("    • review_queue.csv     — pairs flagged for manual review\n")
