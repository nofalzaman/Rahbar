# Put your actual screenshots here

Follow `../SCREENSHOTS.md`. Save uncropped terminal captures as `A1-verification.png`, `A2-zero-chunks.png`, through the B/C/D/E/F names in that guide. Add labelled continuation images when needed.

After completing the human question/review requirements and rerunning the affected evaluation, rebuild the PDF with:

```powershell
python -m scripts.build_ragops_report
```

ReportLab must be installed in that Python environment. The builder adds these images to appendix pages; no screenshots have been generated or supplied by the agent.
