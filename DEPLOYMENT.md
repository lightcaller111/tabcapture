# Mobile website and ongoing updates

The chosen deployment target is **GitHub + Streamlit Community Cloud**. Deployment is not complete until a repository is connected and Streamlit returns a working HTTPS address.

Source repository: https://github.com/lightcaller111/tabcapture
Deployment branch: `main`. Entrypoint: `app.py`. Python: `3.12`.

## Initial connection

1. The owner supplied `lightcaller111/tabcapture` (public). App source belongs at its root, with `app.py` at the root. Do not upload `.venv`, source videos, cached captures, PDFs, credentials, or the `work` folder.
2. Allow the connected GitHub integration to access this repository if it is not visible to the assistant.
3. Sign in at https://share.streamlit.io/ and connect the repository. Select branch `main`, entrypoint `app.py`, and Python 3.12 in Advanced settings.
4. Choose an available app address and deploy. Account linking / OAuth permissions must be reviewed by the owner.
5. Open the deployed HTTPS address on the phone. Use the browser's Share / Add to Home Screen action if desired. This is a browser app; it requires internet access and is not an offline native app.

## Updates requested in this task

Request a change here. The maintenance flow is:

1. Edit the source and increment `version.py`; describe the changes in `CHANGELOG.md`.
2. Run `python -m unittest discover -s tests -v` and inspect any changed PDF output.
3. Commit the verified files to the connected deployment branch.
4. Streamlit detects repository changes and redeploys the existing app. Verify that the existing address reports the new version.
5. Refresh the phone page after downloading any current PDF. No app-store submission or phone reinstall is needed.

GitHub Actions runs the regression suite on pushes and pull requests. Streamlit Community Cloud deployment is independent of that workflow; test before updating the deployment branch. The source repository and deployed URL still need to be recorded here after connection.

`requirements.txt` includes the PyPI `nodejs-wheel` package to supply Node.js 22 or newer; `packages.txt` supplies FFmpeg and Korean fonts. The package redistributes Node.js and is not an official Node.js distribution channel. Background references: https://pypi.org/project/nodejs-wheel-binaries/ and https://github.com/yt-dlp/yt-dlp/wiki/EJS.

## Operational limits

- Keep the phone page open during processing. Sessions and downloaded videos are temporary; restarting or redeploying the server can end an in-progress extraction.
- YouTube may reject requests from a shared hosting provider even when the same URL works on a personal computer. Local video upload remains available.
- Large videos can exceed free-host resources. Start with one song and a one-second sample interval; use a shorter time range for large videos.
- The optional Dockerfile supports another container host if the free host proves unsuitable. That alternative has not been deployed or built in this workspace.

Official references: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy and https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app
