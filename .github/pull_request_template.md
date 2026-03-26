## Summary

- What changed?
- Why does it matter?

## Validation

- [ ] `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v`
- [ ] `ruff check src/openmind tests`
- [ ] `python3 -m compileall src/openmind`
- [ ] `PYTHONPATH=src python3 -m openmind --help`
- [ ] `cd website && npm run build` (if docs or website changed)

## Risk

- Any privacy, token, SSRF, or prompt-injection implications?
- Any docs or public claims that need to be updated?
