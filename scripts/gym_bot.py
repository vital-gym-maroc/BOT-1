import os
import time
import re
import requests
import pandas as pd
import os
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException

# ------------------------
# Configuration
# ------------------------
email = os.getenv("EMAIL")
password = os.getenv("PASSWORD")
DOWNLOAD_DIR = "/home/runner/work/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ------------------------
# Selenium setup
# ------------------------
options = webdriver.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument("--window-size=1920,1080")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")

options.add_experimental_option("prefs", {
    "profile.default_content_setting_values.geolocation": 1,
    "download.default_directory": DOWNLOAD_DIR,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True,
})

service = Service("/usr/local/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=options)
wait = WebDriverWait(driver, 20)




# ------------------------
# Login
# ------------------------
driver.get('https://vita.clubi.ma/login')
time.sleep(3)


email_el = wait.until(EC.presence_of_element_located((By.ID, "email")))
password_el = wait.until(EC.presence_of_element_located((By.ID, "password")))

email_el.clear()
email_el.send_keys(email)
password_el.clear()
password_el.send_keys(password)

time.sleep(2)

try:
    submit_btn = driver.find_element(By.CSS_SELECTOR, "button.submit-btn")
except Exception:
    submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
submit_btn.click()

time.sleep(2)
driver.get('https://vita.clubi.ma/admin/liste-adherents')

all_links = []

while True:
    # --- Scroll to bottom (handle lazy load) ---
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    # --- Extract all links from the ID column ---
    links = driver.find_elements(By.CSS_SELECTOR, "table#data-packs tbody tr td:nth-child(2) a")
    for link in links:
        href = link.get_attribute("href")
        if href and href not in all_links:
            all_links.append(href)

    # --- Go to next page ---
    try:
        next_button = driver.find_element(By.XPATH, "//ul[@class='pagination']//a[@aria-label='Next']")
        parent_li = next_button.find_element(By.XPATH, "..")
        if "disabled" in parent_li.get_attribute("class"):
            print("Reached last page.")
            break
        next_button.click()
        time.sleep(3)
    except NoSuchElementException:
        print("Next button not found, stopping.")
        break
    except ElementClickInterceptedException:
        print("Could not click next button, retrying...")
        time.sleep(1)

# ------------------------
# Create final DataFrame
# ------------------------
df_links = pd.DataFrame(all_links, columns=["Lien_ID"])


from bs4 import BeautifulSoup
import pandas as pd
import time

all_data = []  # store all rows

links = df_links['Lien_ID'].astype(str).str.strip().tolist()

for d in links:
    print("Visiting:", d)
    
    attempt = 0
    max_attempts = 2  # try twice if first fails
    
    while attempt < max_attempts:
        try:
            # Load the page
            driver.get(d)
            time.sleep(3)  # ⏳ wait for 3 seconds to ensure the page fully loads

            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            data = {}

            # ---------- 1. Personal info ----------
            name_tag = soup.find('h2')
            data['Nom'] = name_tag.get_text(strip=True) if name_tag else ''

            status_tag = soup.find('span', class_='adherent-status')
            data['Statut'] = status_tag.get_text(strip=True) if status_tag else ''

            for p in soup.select('div.flex-2.info-tablette p, div.flex-3.info-tablette p'):
                b_tag = p.find('b')
                span_tag = p.find('span')
                if b_tag and span_tag:
                    label = b_tag.get_text(strip=True).replace(" :", "")
                    value = span_tag.get_text(strip=True)
                    data[label] = value

            # ---------- 2. Abonnement info ----------
            for row in soup.select('div.border-none.abonnement-actule div.col-md-12'):
                label_tag = row.select_one('p.font-weight-semibold')
                if not label_tag:
                    continue
                label = label_tag.get_text(strip=True).replace(" :", "")

                value_tags = row.select('div.wrapper p.font-weight-semibolds, div.wrapper span')
                values = [v.get_text(strip=True) for v in value_tags if v.get_text(strip=True)]
                if not values:
                    wrapper = row.select_one('div.wrapper')
                    if wrapper:
                        values = [wrapper.get_text(strip=True)]

                data[label] = ", ".join(values)

            # ---------- 3. Payment summary ----------
            for card in soup.select('div.row div.cards'):
                title_tag = card.select_one('h4.card-title')
                value_tag = card.select_one('h3.font-weight-medium')
                if title_tag and value_tag:
                    data[title_tag.get_text(strip=True)] = value_tag.get_text(strip=True)

            all_data.append(data)  # add row
            print("✅ Data collected successfully.\n")
            time.sleep(2)  # ⏳ wait 2 seconds before going to the next link
            break  # success, exit retry loop

        except Exception as e:
            attempt += 1
            print(f"⚠️ Attempt {attempt} failed for {d}. Error: {e}")
            time.sleep(3)  # wait 3 seconds before retrying
            if attempt == max_attempts:
                print(f"❌ Skipping {d} after {max_attempts} failed attempts.\n")
                break

# ---------- 4. Create DataFrame ----------
df = pd.DataFrame(all_data)
df['Jours restants'] = df['Jours restants'].apply(lambda x: str(x).split(',')[0].strip() if pd.notnull(x) else x)
df['Les frais ajoutés'] = df['Les frais ajoutés'].apply(lambda x: str(x).split(',')[0].strip() if pd.notnull(x) else x)

# Columns to fix
phone_cols = ['Téléphone', "Téléphone d'urgence"]

for col in phone_cols:
    df[col] = df[col].apply(
        lambda x: f"0{int(x)}" if pd.notnull(x) and str(x).strip().isdigit() else x
    )

#df = df.drop(columns=['Unnamed: 0'])

# Set 'ID' as the index
cols = ['ID'] + [c for c in df.columns if c != 'ID']
df = df[cols]
df = df.replace([float('inf'), float('-inf')], None)
df = df.fillna('')


print("Scraping finished. Total records:", len(df))

import pandas as pd
from google.oauth2.service_account import Credentials
import gspread
from gspread_formatting import *
import os

# ======================
# Google Sheets setup
# ======================
service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
client = gspread.authorize(credentials)

SPREADSHEET_URL = os.environ["SPREADSHEET_URL"]
WORKSHEET_NAME = 'Main'

# ======================
# Split DataFrame
# ======================
df_actif = df[df["Statut"] == "actif"]
df_inactif = df[df["Statut"] == "inactif"]

# ======================
# Spreadsheet URL
# ======================
spreadsheet_url = os.getenv("SPREADSHEET_URL")
spreadsheet = client.open_by_url(spreadsheet_url)

# ======================
# Function to upload DF to a sheet with formatting
# ======================
def upload_df_to_sheet(df, sheet_name, color_rgb):
    # Get or create the worksheet
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.clear()
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=str(len(df)+10), cols=str(len(df.columns)+5))
    
    # Upload data (header + values)
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())

    # Apply borders
    rows, cols = df.shape
    total_rows = rows + 1  # include header
    cell_range = f"A1:{gspread.utils.rowcol_to_a1(total_rows, cols)}"

    border_style = Border(style="SOLID", color=Color(0, 0, 0))
    fmt_borders = CellFormat(
        borders=Borders(top=border_style, bottom=border_style, left=border_style, right=border_style)
    )
    format_cell_range(worksheet, cell_range, fmt_borders)

    # Header formatting
    header_format = CellFormat(
        backgroundColor=Color(*color_rgb),
        textFormat=TextFormat(bold=True)
    )
    format_cell_range(worksheet, "1:1", header_format)

    print(f"✅ Sheet '{sheet_name}' updated successfully!")

# ======================
# Upload sheets
# ======================
# Light green header for actif
upload_df_to_sheet(df_actif, "Actif", (0.8, 1, 0.8))

# Light red header for inactif
upload_df_to_sheet(df_inactif, "Inactif", (1, 0.8, 0.8))

# Light blue header for main sheet (all data)
upload_df_to_sheet(df, "Main", (0.8, 0.9, 1))

print("✅ All sheets updated in the same spreadsheet!")

