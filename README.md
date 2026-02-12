# Entity Resolution System

A customer record entity resolution system that implements fuzzy matching (Levenshtein, Jaro-Winkler) to identify duplicate customer records across two datasets.

## Features

- **Fuzzy Matching**: Uses RapidFuzz for string similarity (Levenshtein, Jaro-Winkler, Token Sort)
- **Blocking Strategies**: ZIP code, name prefix, soundex, and multi-block approaches to scale to large tables
- **Conflict Resolution**: Intelligent merge logic for combining duplicate records
- **Match Statistics**: Comprehensive reporting and match quality analysis

## Requirements

- Python 3.9+
- pandas
- numpy
- rapidfuzz

## Installation

```bash
pip install pandas numpy rapidfuzz
```

## Usage

```bash
python entity_resolution.py
```

This will:
1. Load customer records from `customers_a.csv` and `customers_b.csv`
2. Apply blocking and fuzzy matching to identify duplicates
3. Generate a merged output with de-duplicated records
4. Save results to `output/` directory

## Output Files

- `merged_output.csv` - De-duplicated master table
- `all_comparisons.csv` - All pair scores and comparison details
- `review_queue.csv` - Pairs flagged for manual review

## Configuration

Adjust these parameters in the script:

```python
resolver = EntityResolver(
    path_a            = "customers_a.csv",
    path_b            = "customers_b.csv",
    match_threshold   = 0.70,      # Minimum score to consider a match
    review_threshold  = 0.50,      # Score below this for manual review
    blocking_strategy = "multi",   # 'multi' | 'zip' | 'name_prefix' | 'soundex' | 'none'
    verbose           = True,
)
```

## License

MIT
