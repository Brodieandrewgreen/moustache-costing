
import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Moustache • Costing & GP", layout="wide", page_icon="🧔")

# --- Branding Header
col_logo, col_title = st.columns([1,4])
with col_logo:
    st.image("assets/logo.svg", use_column_width=True)
with col_title:
    st.title("Moustache • Costing & GP Tool")
    st.caption("Simple, fast costings for kitchen & bar.")

# --- Auth
def check_auth():
    # Prefer secrets in hosted mode
    email = st.secrets.get("auth", {}).get("email", None)
    password = st.secrets.get("auth", {}).get("password", None)

    if not email or not password:
        st.info("Authentication not configured. Using fallback password form.")
        email = st.session_state.get("email_input", "")
        pwd_ok = "auth_ok" in st.session_state and st.session_state["auth_ok"]
        if not pwd_ok:
            with st.form("login"):
                st.text_input("Email", key="email_input")
                st.text_input("Password", type="password", key="password_input")
                submitted = st.form_submit_button("Login")
                if submitted:
                    # Fallback default credentials for local dev ONLY
                    if st.session_state.get("email_input") and st.session_state.get("password_input"):
                        st.session_state["auth_ok"] = True
                        st.experimental_rerun()
            st.stop()
        return True
    else:
        # Hosted: ask for credentials and compare to secrets
        if "auth_ok" not in st.session_state:
            with st.form("login"):
                st.text_input("Email", key="email_input")
                st.text_input("Password", type="password", key="password_input")
                submitted = st.form_submit_button("Login")
                if submitted:
                    if st.session_state.get("email_input","").strip().lower() == email.strip().lower() and st.session_state.get("password_input")==password:
                        st.session_state["auth_ok"] = True
                        st.experimental_rerun()
        if not st.session_state.get("auth_ok"):
            st.stop()
        return True

check_auth()

st.success("Logged in")

# --- Paths & defaults
WORKBOOK_PATH = Path("Moustache_Costing_MVP.xlsx")

# --- Load or upload workbook
@st.cache_data
def load_book(path: Path):
    xls = pd.ExcelFile(path)
    return {name: pd.read_excel(xls, name) for name in xls.sheet_names}

def save_book(dfs):
    with pd.ExcelWriter(WORKBOOK_PATH, engine="xlsxwriter") as writer:
        for name, df in dfs.items():
            df.to_excel(writer, sheet_name=name, index=False)

# --- Business logic
def calc_recipe_costs(dfs):
    GST_RATE = float(dfs["Settings"].loc[dfs["Settings"]["key"]=="gst_rate","value"].iloc[0])
    target_gp = float(dfs["Settings"].loc[dfs["Settings"]["key"]=="target_gp_pct","value"].iloc[0])

    skus = dfs["SKUs"].copy()
    conv = dfs["Conversions"].copy()
    bom = dfs["Recipe_BOM"].copy()

    conv_map = dict(zip(conv["from_uom"], conv["multiplier_per_unit"]))
    # Unit cost helper in case it's missing
    if "unit_cost_ex_gst" not in skus.columns:
        def unit_cost_ex_gst(row):
            mult = conv_map.get(row["pack_uom"], 1)
            total_base = row["pack_size"] * mult
            cost_ex = row["pack_cost_inc_gst"] / 1.10
            eff_units = total_base * row.get("yield_pct",1)
            return cost_ex / max(eff_units,1e-9)
        skus["unit_cost_ex_gst"] = skus.apply(unit_cost_ex_gst, axis=1)

    cost_map = dict(zip(skus["sku_name"], skus["unit_cost_ex_gst"]))
    uom_map = dict(zip(skus["sku_name"], skus["base_uom"]))

    def qty_base(row): return row["qty"] * conv_map.get(row["uom"], 1)

    bom["qty_base"] = bom.apply(qty_base, axis=1)
    bom["base_uom"] = bom["sku_name"].map(uom_map)
    bom["unit_cost_ex_gst"] = bom["sku_name"].map(cost_map)
    bom["line_cost_ex_gst"] = bom["qty_base"] * bom["unit_cost_ex_gst"]

    recipes = bom.groupby("recipe", as_index=False)["line_cost_ex_gst"].sum()
    recipes.rename(columns={"line_cost_ex_gst":"food_cost_ex_gst"}, inplace=True)
    recipes["food_cost_inc_gst"] = recipes["food_cost_ex_gst"] * 1.10
    recipes["target_gp_pct"] = target_gp
    recipes["suggested_price_inc_gst"] = (recipes["food_cost_inc_gst"] / (1 - recipes["target_gp_pct"])).round(2)

    dfs["Recipe_BOM"] = bom
    dfs["Recipes"] = recipes

    if "Menu" in dfs:
        menu = dfs["Menu"].copy()
        drop_cols = ["food_cost_ex_gst","food_cost_inc_gst","suggested_price_inc_gst","achieved_gp_pct","contribution_margin_inc_gst"]
        menu = menu.drop(columns=[c for c in drop_cols if c in menu.columns], errors="ignore")
        menu = menu.merge(recipes[["recipe","food_cost_ex_gst","food_cost_inc_gst","suggested_price_inc_gst","target_gp_pct"]], on="recipe", how="left")
        if "sell_price_inc_gst" not in menu.columns:
            menu["sell_price_inc_gst"] = menu["suggested_price_inc_gst"]
        menu["achieved_gp_pct"] = 1 - (menu["food_cost_inc_gst"] / menu["sell_price_inc_gst"])
        menu["contribution_margin_inc_gst"] = (menu["sell_price_inc_gst"] - menu["food_cost_inc_gst"]).round(2)
        dfs["Menu"] = menu

    return dfs

def calc_dashboard(dfs):
    if "SalesMix" not in dfs or "Menu" not in dfs:
        return pd.DataFrame({"Metric":[],"Value":[]})
    mix = dfs["SalesMix"].merge(dfs["Menu"], left_on="item", right_on="recipe", how="left")
    mix["revenue_inc_gst"] = mix["qty_sold"] * mix["sell_price_inc_gst"]
    mix["cost_inc_gst"] = mix["qty_sold"] * mix["food_cost_inc_gst"]
    mix["profit_inc_gst"] = mix["revenue_inc_gst"] - mix["cost_inc_gst"]
    gp = 1 - (mix["cost_inc_gst"].sum() / mix["revenue_inc_gst"].sum()) if mix["revenue_inc_gst"].sum() else 0.0
    return pd.DataFrame({
        "Metric": ["Total Revenue (inc GST)", "Total Cost (inc GST)", "Total Profit (inc GST)", "Weighted GP %"],
        "Value": [round(mix["revenue_inc_gst"].sum(),2), round(mix["cost_inc_gst"].sum(),2), round(mix["profit_inc_gst"].sum(),2), round(gp,3)]
    })

# --- Data bootstrap
workbook = Path("Moustache_Costing_MVP.xlsx")
if not workbook.exists():
    st.warning("Workbook not found. Upload your Excel file to begin.")
    upl = st.file_uploader("Upload Moustache_Costing_MVP.xlsx", type=["xlsx"])
    if upl:
        workbook.write_bytes(upl.read())
        st.experimental_rerun()
    st.stop()

dfs = load_book(workbook)
dfs = calc_recipe_costs(dfs)

# --- UI Tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Dashboard","Menu","Recipes","Recipe BOM","SKUs","Settings"])

with tab1:
    st.subheader("Snapshot")
    dash = calc_dashboard(dfs)
    st.dataframe(dash, use_container_width=True)
    st.caption("Weighted GP uses current SalesMix × Menu pricing.")
    st.subheader("Sales Mix")
    dfs["SalesMix"] = st.data_editor(dfs["SalesMix"], use_container_width=True, num_rows="dynamic")

with tab2:
    st.subheader("Menu & Pricing")
    dfs["Menu"] = st.data_editor(dfs["Menu"], use_container_width=True, num_rows="dynamic")

with tab3:
    st.subheader("Recipe Cost Summary")
    st.dataframe(dfs["Recipes"], use_container_width=True)

with tab4:
    st.subheader("Recipe Bill of Materials")
    dfs["Recipe_BOM"] = st.data_editor(dfs["Recipe_BOM"], use_container_width=True, num_rows="dynamic")

with tab5:
    st.subheader("SKUs (Ingredients & Beverages)")
    dfs["SKUs"] = st.data_editor(dfs["SKUs"], use_container_width=True, num_rows="dynamic")

with tab6:
    st.subheader("Settings")
    dfs["Settings"] = st.data_editor(dfs["Settings"], use_container_width=True)

st.divider()
if st.button("💾 Save workbook"):
    dfs = calc_recipe_costs(dfs)
    save_book(dfs)
    st.success("Saved")
    st.download_button("Download updated workbook", data=open(workbook,"rb").read(), file_name="Moustache_Costing_MVP.xlsx")
