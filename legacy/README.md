# Legacy Streamlit prototype (archived)

These files are the earlier Streamlit prototype. They are kept for reference only and are **not run**.

`database.py` used integer IDs and conflicting `documents`/`versions` tables in the same
`data/safesop.db` file as `api.py`. The canonical schema now lives in `api.py` (`init_db`),
which absorbed the useful parts of this design (`evaluations`, `review_history`, `parent_version_id`).
