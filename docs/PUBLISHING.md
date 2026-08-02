# Publishing to GitHub

## Review first

```bash
python3 tools/audit_public_repo.py .
git status --short
git diff --cached
```

Verify author metadata, licenses, private-path removal, credentials, and the
redistribution rights for every figure and video.

## Authenticate

```bash
gh auth login
gh auth status
```

## Create and push the public repository

```bash
./PUSH_PUBLIC_GITHUB.sh OWNER malonaldehyde-transition-sampling I_UNDERSTAND_THIS_WILL_BE_PUBLIC
```

## Publish large media

```bash
gh release create v0.1.0 /path/to/release_assets/* \
  --repo OWNER/malonaldehyde-transition-sampling \
  --title "Initial public release" \
  --notes "Initial public release of figures and videos."
```
