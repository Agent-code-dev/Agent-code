# Agent Code 2.2.0

## Highlights

- Added project-level ignore support through `.agentignore`, alongside `.gitignore`, so project discovery can avoid generated files, large assets, vendored code, and other irrelevant paths.
- Ignore rules are applied during bounded project analysis and the active ignore files/rule count are reported in project context.
- Hard safety exclusions remain non-overridable: ignore negation cannot make `.env`, credential, SSH, or other sensitive paths eligible for project discovery.
- Added regression tests for ignore behavior and sensitive-file exclusions.
- Added conservative test-command discovery for Python, Rust, Go, and Node projects. Node package scripts are never run automatically: they always require a direct approval, even in Auto permission mode.
- Added GitHub Actions CI for automated testing. PyPI publishing and GitHub Releases remain manual.

## Versioning note

This is the next release after 2.1.8. The project already has a 2.0.0 release line, so the correct forward version is 2.2.0 rather than reusing the existing 2.0.0 version/tag.

## Validation

The validation helper recognizes Python, Cargo, Go, and Node package-manager test scripts. It does not install dependencies, configure CMake projects, or execute unrecognized commands.

See `TEST-RESULTS-2.2.0.md` for the exact test command, result, and any environment limitations. GUI and provider integrations must be tested in an environment with their optional/runtime dependencies and real provider credentials.
