"""LMS test isolation lives in `tests/lms/isolation.py` (`reset_lms_state`, the cleanup list older design docs call
"tests/lms/conftest.py cleanup"); it runs from the autouse `clean_lms_tables` fixture in `tests/conftest.py`.

Do not define LMS-wide fixtures here: with interleaved command-line paths (`tests/lms/a.py tests/b.py tests/lms/c.py`)
pytest builds a second `tests/lms` package node that does not see this conftest's fixtures."""
