import random
import time
import unicodedata
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    NoSuchElementException,
)

# Link Google Form của cậu
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSegOZaWE2RIlEvIkHn4M-K5EkVbQOVx7YbllIBs1jCW05sE2w/viewform"

# Tổng số lần muốn gửi
TOTAL_SUBMISSIONS = 20

TIMEOUT = 15

# Nhãn đã chuẩn hóa (không dấu, chữ thường) - so khớp CHÍNH XÁC
NEXT_LABELS = {"tiep", "next"}
SUBMIT_LABELS = {"gui", "submit"}
BACK_LABELS = {"quay lai", "back"}
CLEAR_LABELS = {
    "xoa het cau tra loi trong bieu mau",
    "xoa het cau tra loi",
    "xoa cau tra loi",
    "xoa bieu mau",
    "clear form",
    "clear answers",
}
CONFIRM_MARKERS = [
    "cau tra loi cua ban da duoc ghi lai",
    "cau tra loi cua ban da duoc ghi nhan",
    "your response has been recorded",
]

NAV_XPATH = "//form//div[@role='button']"


def normalize(text):
  if not text:
    return ""
  text = text.replace("đ", "d").replace("Đ", "D")
  text = unicodedata.normalize("NFD", text)
  text = "".join(c for c in text if unicodedata.category(c) != "Mn")
  return " ".join(text.lower().split())


def button_label(el):
  # textContent đọc được cả chữ trong span lồng nhau
  raw = (
      el.get_attribute("textContent")
      or el.get_attribute("innerText")
      or el.get_attribute("aria-label")
      or ""
  )
  label = normalize(raw)
  if not label:
    label = normalize(el.get_attribute("aria-label") or "")
  return label


def dump_nav_candidates(driver):
  print("=== Các phần tử role='button' tìm thấy ===")
  for idx, el in enumerate(driver.find_elements(By.CSS_SELECTOR, "[role='button']")):
    try:
      html = (el.get_attribute("outerHTML") or "")[:200].replace("\n", " ")
      print(
          f"[{idx}] tag={el.tag_name} role={el.get_attribute('role')} "
          f"aria-label={el.get_attribute('aria-label')!r} "
          f"innerText={(el.get_attribute('innerText') or '').strip()!r} "
          f"displayed={el.is_displayed()}\n     outerHTML={html}"
      )
    except StaleElementReferenceException:
      print(f"[{idx}] <stale>")


def report_invalid(driver):
  """In các câu hỏi đang báo lỗi validation trên trang hiện tại."""
  found = False
  for q in driver.find_elements(By.XPATH, "//form//div[@role='listitem']"):
    try:
      if not q.is_displayed():
        continue
      alerts = [
          (a.get_attribute("textContent") or "").strip()
          for a in q.find_elements(By.XPATH, ".//*[@role='alert']")
      ]
      alerts = [a for a in alerts if a]
      invalid_inputs = q.find_elements(By.XPATH, ".//*[@aria-invalid='true']")
      if alerts or invalid_inputs:
        found = True
        title = (q.get_attribute("textContent") or "").strip()[:100]
        print(f"[LỖI] Câu: {title!r} | thông báo: {alerts}")
        print(
            "      outerHTML:",
            (q.get_attribute("outerHTML") or "")[:400].replace("\n", " "),
        )
    except StaleElementReferenceException:
      continue
  if not found:
    print("[INFO] Không thấy thông báo lỗi validation nào.")


def find_button(driver, labels, timeout=TIMEOUT):
  """Trả về nút hiển thị có nhãn chuẩn hóa khớp chính xác; None nếu không có."""

  def _locate(d):
    for el in d.find_elements(By.XPATH, NAV_XPATH):
      try:
        if not el.is_displayed():
          continue
        label = button_label(el)
        if label in CLEAR_LABELS or label in BACK_LABELS:
          continue
        if label in labels:
          return el
      except StaleElementReferenceException:
        continue
    return False

  try:
    return WebDriverWait(driver, timeout).until(_locate)
  except TimeoutException:
    return None


def safe_click(driver, el):
  label = button_label(el)
  if label in CLEAR_LABELS or label in BACK_LABELS:
    raise RuntimeError(f"Từ chối bấm nút không hợp lệ: {label!r}")
  driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
  WebDriverWait(driver, TIMEOUT).until(
      lambda d: el.is_displayed() and el.is_enabled()
  )
  driver.execute_script("arguments[0].click();", el)


def page_signature(driver):
  try:
    items = driver.find_elements(By.XPATH, "//form//div[@role='listitem']")
    return tuple(
        (i.get_attribute("textContent") or "").strip()[:80]
        for i in items
        if i.is_displayed()
    )
  except StaleElementReferenceException:
    return ()


def is_submitted(driver):
  try:
    body = normalize(
        driver.find_element(By.TAG_NAME, "body").get_attribute("textContent")
    )
  except Exception:
    return False
  return any(m in body for m in CONFIRM_MARKERS)


def click_next(driver):
  before = page_signature(driver)
  btn = find_button(driver, NEXT_LABELS)
  if btn is None:
    dump_nav_candidates(driver)
    raise NoSuchElementException("Không tìm thấy nút Tiếp/Next.")
  label = button_label(btn)
  safe_click(driver, btn)

  def _changed(d):
    try:
      btn.is_displayed()
    except StaleElementReferenceException:
      return True
    return page_signature(d) != before

  try:
    WebDriverWait(driver, 8).until(_changed)
  except TimeoutException:
    report_invalid(driver)
    raise TimeoutException(
        "Đã bấm Tiếp nhưng trang không chuyển (xem danh sách câu lỗi ở trên)."
    )
  print(f"Đã bấm Tiếp [{label}] và trang đã chuyển.")


def click_submit(driver):
  btn = find_button(driver, SUBMIT_LABELS)
  if btn is None:
    dump_nav_candidates(driver)
    raise NoSuchElementException("Không tìm thấy nút Gửi/Submit.")
  label = button_label(btn)
  safe_click(driver, btn)
  try:
    WebDriverWait(driver, TIMEOUT).until(is_submitted)
  except TimeoutException:
    report_invalid(driver)
    dump_nav_candidates(driver)
    raise TimeoutException("Đã bấm Gửi nhưng KHÔNG thấy xác nhận của Google Forms.")
  print(f"Đã bấm Gửi [{label}] và có xác nhận.")


def not_other(elements):
  """Loại ô 'Khác:' (bắt buộc nhập chữ) khỏi danh sách lựa chọn ngẫu nhiên."""
  ok = [e for e in elements if e.get_attribute("data-value") != "__other_option__"]
  return ok or elements


def fill_current_page(driver):
  # --- Logic điền câu trả lời cũ (chỉ thêm not_other) ---
  questions = driver.find_elements(By.XPATH, "//div[@role='listitem']")
  for q in questions:
    try:
      # Xử lý dạng bảng ma trận (Nhiều hàng)
      radiogroups = q.find_elements(By.XPATH, ".//div[@role='radiogroup']")
      if len(radiogroups) > 1:
        for rg in radiogroups:
          radios = rg.find_elements(By.XPATH, ".//div[@role='radio']")
          if radios:
            chosen = random.choice(not_other(radios))
            driver.execute_script("arguments[0].click();", chosen)
            time.sleep(0.05)
        continue

      # Xử lý trắc nghiệm thông thường (Ô tròn đơn)
      radios = q.find_elements(By.XPATH, ".//div[@role='radio']")
      if radios and len(radiogroups) <= 1:
        chosen = random.choice(not_other(radios))
        driver.execute_script("arguments[0].click();", chosen)
        continue

      # Xử lý hộp kiểm (Ô vuông - Chọn ngẫu nhiên 2 đáp án)
      checkboxes = q.find_elements(By.XPATH, ".//div[@role='checkbox']")
      if checkboxes:
        checkboxes = not_other(checkboxes)
        num_to_choose = min(2, len(checkboxes))
        chosen_cb = random.sample(checkboxes, num_to_choose)
        for cb in chosen_cb:
          driver.execute_script("arguments[0].click();", cb)
          time.sleep(0.05)
        continue
    except Exception:
      pass


def run_bot():
  success_count = 0
  for i in range(1, TOTAL_SUBMISSIONS + 1):
    print(f"\n--- Bắt đầu lượt gửi thứ {i}/{TOTAL_SUBMISSIONS} ---")

    options = webdriver.ChromeOptions()
    options.add_argument("--incognito")
    # options.add_argument("--headless")

    driver = webdriver.Chrome(options=options)
    try:
      driver.get(FORM_URL)
      WebDriverWait(driver, TIMEOUT).until(
          EC.presence_of_element_located((By.XPATH, "//form//div[@role='listitem']"))
      )

      submitted = False
      for page in range(1, 11):
        fill_current_page(driver)

        # Trang cuối: có nút Gửi
        if find_button(driver, SUBMIT_LABELS, timeout=2) is not None:
          click_submit(driver)
          submitted = True
          break

        click_next(driver)

      if submitted:
        success_count += 1
        print(f"-> Gửi thành công lượt {i}!")
      else:
        print(f"-> Lượt {i} KHÔNG gửi được: hết số trang tối đa.")

    except Exception as e:
      print(f"Lỗi ở lượt gửi {i}: {type(e).__name__}: {e}")
    finally:
      time.sleep(1.5)
      driver.quit()

    if i < TOTAL_SUBMISSIONS:
      print("Đang chờ 5 giây trước khi mở tab mới...\n")
      time.sleep(5)

  print(f"\nKết thúc: {success_count}/{TOTAL_SUBMISSIONS} lượt gửi có xác nhận.")


if __name__ == "__main__":
  run_bot()