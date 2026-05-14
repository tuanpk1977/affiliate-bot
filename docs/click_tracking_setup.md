# Click Tracking Setup Cho Netlify Drop

Muc tieu: site deploy bang Netlify Drop van luu duoc click vao Google Sheet, khong bat buoc Netlify Functions.

## A. Tao Google Sheet

1. Tao Google Sheet moi.
2. Dat ten file:

```text
affiliate_click_events
```

3. Dat ten tab dau tien:

```text
click_events
```

## B. Dan Apps Script

1. Trong Google Sheet, bam `Extensions`.
2. Bam `Apps Script`.
3. Xoa code mac dinh.
4. Copy toan bo code trong:

```text
scripts/google_sheet_click_webhook.gs
```

5. Dan vao Apps Script.
6. Bam Save.

## C. Deploy Web App

1. Bam `Deploy`.
2. Chon `New deployment`.
3. Select type: `Web app`.
4. Chon:

```text
Execute as: Me
Who has access: Anyone
```

5. Bam `Deploy`.
6. Chap nhan quyen truy cap neu Google hoi.
7. Copy `Web App URL`.

URL dung thuong co dang:

```text
https://script.google.com/macros/s/xxxxx/exec
```

## D. Tao hoac cap nhat file .env

O project root `D:\AFFILATE BOT`, tao/cap nhat file:

```text
.env
```

Them dong:

```text
CLICK_WEBHOOK_URL=<web app url>
```

Vi du:

```text
CLICK_WEBHOOK_URL=https://script.google.com/macros/s/xxxxx/exec
```

Quan trong: voi Netlify Drop, bien Netlify Environment Variables khong tu nhung vao file HTML static. Ban phai set `CLICK_WEBHOOK_URL` trong `.env` truoc khi chay `python main.py`.

## E. Test Webhook Local

Chay:

```powershell
python scripts/test_click_webhook.py "<web app url>"
```

Neu thanh cong, script in:

```text
SUCCESS
HTTP status: 200
```

Google Sheet se co dong moi voi:

```text
tool_slug = cursor
```

Neu chi muon test script khong can internet/webhook that:

```powershell
python scripts/test_click_webhook.py MOCK
```

## F. Build Lai Site

Chay:

```powershell
python main.py
python scripts/validate_site.py
python scripts/validate_go_pages.py
```

## G. Upload Lai Netlify Drop

Upload lai toan bo thu muc:

```text
site_output/
```

Phai dam bao upload ca:

```text
site_output/go/
```

## H. Test Click That

Mo debug URL:

```text
https://review.mssmileenglish.com/go/cursor/?src=/cursor/&cta=official_site&debug=1
```

Can thay:

```text
webhook_url_configured: true
webhook_status: sent
```

Neu thay:

```text
function_status: 404
```

thi khong sao neu ban deploy bang Netlify Drop. Quan trong la `webhook_status: sent`.

Sau do test redirect that:

```text
https://review.mssmileenglish.com/go/cursor/?src=/cursor/&cta=official_site
```

## Luu Y Rieng Tu

Tracking khong luu:

- IP
- email
- ten nguoi dung
- cookie ca nhan
- thong tin dinh danh ca nhan

Neu chua co `CLICK_WEBHOOK_URL`, `/go/<tool>/` van redirect binh thuong nhung production click chua duoc luu ben vung.
