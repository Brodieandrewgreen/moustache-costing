# Moustache • Costing & GP Tool (Hosted-Ready)

This package is ready to deploy to **Streamlit Cloud** (or run locally).

## 1) Local run
```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
Open the local URL in your browser. Upload your `Moustache_Costing_MVP.xlsx` if prompted.

## 2) Host it (Streamlit Cloud)
1. Create a new **Streamlit Community Cloud** app.
2. Upload all files in this folder (including `assets/` and `.streamlit/`).
3. In the Cloud app **Secrets**, paste:
```
[auth]
email = "Brodie.green@gmail.com"
password = "Oddie5366"
[app]
gst_rate = 0.10
target_gp_pct = 0.72
```
4. Deploy. You’ll log in with the email + password above.
5. **Important:** Change the password after first login.

## Notes
- The app reads/writes your Excel workbook in the app root.
- For production, use Streamlit Cloud secrets (not hard-coded passwords).
- To add other users later, we can switch to Google Sign-In or per-user passwords.