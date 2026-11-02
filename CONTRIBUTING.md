# Contributing to eemkit

Thank you for helping. Questions, bug reports, new instrument formats and
corrections to the science are all welcome.

## Reporting a problem or asking for help

Open an [issue](https://github.com/LowCostSensor/eemkit/issues) with:

* what you ran (code, or the steps in the desktop application);
* what you expected and what happened, with the full error message;
* the eemkit version (`python -c "import eemkit; print(eemkit.__version__)"`)
  and your operating system;
* if possible, one input file that shows the problem. Do not attach data you
  are not allowed to share.

For a new instrument format, attach an example export and the instrument
model and software version.

## Changing the code

```bash
git clone https://github.com/LowCostSensor/eemkit
cd eemkit
pip install -e ".[dev,docs]"
pytest              # tests
ruff check src tests
mkdocs serve        # documentation preview at http://127.0.0.1:8000
```

1. Open an issue first for anything larger than a small fix, so the approach
   can be agreed.
2. Work on a branch and open a pull request against `main`.
3. Add tests for new behaviour; the test suite must pass and `ruff` must be
   clean.
4. Code, docstrings and documentation are in English. Match the style of the
   surrounding code.

## Scientific choices

eemkit avoids silent defaults for values that depend on the measurement, and
every method cites its source. A change to a correction, an index or a
PARAFAC diagnostic should:

* cite the publication it follows, in the docstring and in `docs/`;
* keep the result recorded in the processing history (`with_history`);
* say in the pull request how the result changes on existing data.

## Code of conduct

Be respectful and constructive. Harassment or personal attacks are not
accepted; maintainers may remove comments or contributors that break this rule.
