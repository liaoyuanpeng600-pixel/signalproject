# Release Checklist

## Pre-release

- [x] Working tree is clean
- [x] Full test suite passes locally
- [x] Supported Python CI matrix passes
- [x] Version metadata is consistent
- [x] README reflects current capabilities
- [x] Release notes are prepared
- [x] Wheel and sdist build successfully
- [x] Twine check passes
- [x] Wheel installs in a clean environment
- [x] Installed public package imports succeed

## Release

- [ ] Create annotated version tag
- [ ] Push version tag
- [ ] Create GitHub Release
- [ ] Attach or publish approved artifacts

## Post-release

- [ ] Verify the GitHub Release page
- [ ] Verify installation instructions
- [ ] Record the next development version
