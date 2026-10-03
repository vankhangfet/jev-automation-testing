# Setup môi trường Android E2E (Windows)

Runbook cho Task 13: chạy E2E smoke `flows/login_smoke.yaml` trên Android emulator
qua Appium (UiAutomator2). Các mục đánh dấu **[ĐÃ SẴN]** đã được kiểm tra/cài trên
máy này ngày 2026-10-03; các mục **[USER]** cần bạn tự làm (GUI/API key).

## 0. Hiện trạng máy này (kiểm tra 2026-10-03)

| Thành phần | Trạng thái |
|---|---|
| Node.js | **[ĐÃ SẴN]** v22.16.0 |
| Appium (global npm) | **[ĐÃ SẴN]** 3.8.0 (`C:\home\khang\.npm-global`) |
| Driver uiautomator2 | **[ĐÃ SẴN]** 7.6.2 |
| Java 17 + JAVA_HOME | **[ĐÃ SẴN]** Temurin 17.0.18, `JAVA_HOME` đã trỏ đúng |
| ANDROID_HOME | **[USER]** chưa set — kẹt chính; cần Android Studio (mục 3) |
| adb | có bản standalone tại `C:\platform-tools` (trên PATH) nhưng **không phải** SDK đầy đủ — doctor vẫn báo thiếu |
| APK Now in Android | **[USER]** repo `android/nowinandroid` **không đính kèm asset APK nào** trong releases (đã kiểm bằng `gh`: cả 0.1.1 lẫn 0.0.5 đều rỗng) → phải build từ nguồn hoặc cài từ Play Store (mục 4) |

## 1. Node.js + Appium server — [ĐÃ SẴN]

```powershell
node --version          # cần >= 18 (máy này v22.16.0)
npm install -g appium   # đã cài: 3.8.0; npm prefix là thư mục user nên không cần admin
appium driver install uiautomator2   # đã cài: 7.6.2 (lưu ý tên driver là "uiautomator2")
appium driver doctor uiautomator2    # kiểm tra thiếu gì thì bổ sung (JAVA_HOME, ANDROID_HOME)
```

Kết quả `appium driver doctor uiautomator2` gần nhất trên máy này:

```
✔ JAVA_HOME is set to: C:\Program Files\Eclipse Adoptium\jdk-17.0.18.8-hotspot\
✔ 'bin\java.exe' exists under 'C:\Program Files\Eclipse Adoptium\jdk-17.0.18.8-hotspot\'
✔ ffmpeg.exe exists at: C:\ffmpeg\bin\ffmpeg.exe'
✖ ANDROID_HOME environment variable is NOT set!
✖ adb, emulator could not be found because ANDROID_HOME is NOT set!
✖ bundletool.jar cannot be found                       (optional)
✖ gst-launch-1.0.exe and/or gst-inspect-1.0.exe ...    (optional)
→ 2 required fixes needed, 2 optional fixes possible.
```

2 mục bắt buộc còn thiếu đều do chưa có Android SDK (mục 3). bundletool (xử lý
.app bundle) và GStreamer (stream màn hình) là tùy chọn — smoke test không cần.

## 2. Java 17 (UiAutomator2 cần) — [ĐÃ SẴN]

Máy này đã có Temurin 17.0.18 với `JAVA_HOME` trỏ đúng. Nếu setup máy mới:

```powershell
winget install EclipseAdoptium.Temurin.17.JDK
# set JAVA_HOME trỏ tới thư mục JDK cài thật, VD:
# C:\Program Files\Eclipse Adoptium\jdk-17.0.18.8-hotspot\
java -version   # phải ra 17.x
```

## 3. Android SDK + Emulator — [USER, bắt buộc]

1. Cài Android Studio (GUI): https://developer.android.com/studio
   (đây là installer GUI nên không tự động hóa được trong task headless này).
2. Trong Android Studio → **SDK Manager**: cài
   - Android SDK Platform 34
   - Android SDK Platform-Tools
   - Android Emulator
   - Android SDK Build-Tools 34
3. Set biến môi trường user `ANDROID_HOME` (và thêm `%ANDROID_HOME%\platform-tools`
   vào PATH nếu muốn). Vị trí SDK mặc định:
   `C:\Users\<you>\AppData\Local\Android\Sdk`
   (PowerShell: `setx ANDROID_HOME "C:\Users\<you>\AppData\Local\Android\Sdk"`,
   sau đó **mở lại terminal** để nhận biến mới.)
4. Kiểm tra lại: `appium driver doctor uiautomator2` — hai WARN về ANDROID_HOME phải hết.
5. Trong **Device Manager**: tạo AVD (VD: Pixel 7, API 34, image không cần Google APIs cũng được).
6. Khởi động emulator và **giữ nguyên trong suốt run**. Xác nhận:

```powershell
adb devices    # phải thấy dòng "emulator-5554  device"
```

## 4. App mẫu: Now in Android — [USER, bắt buộc]

Repo upstream **không phát hành APK trong GitHub Releases** (các release 0.1.1 /
0.0.5 đều không có asset). Hai phương án:

**Phương án A (khuyên dùng) — build từ nguồn** (cần JDK 17 + Android SDK ở mục 2–3):

```powershell
git clone https://github.com/android/nowinandroid C:\Working\nowinandroid
cd C:\Working\nowinandroid
.\gradlew.bat :app:assembleProdDebug
# APK xuất ra: app\build\outputs\apk\prod\debug\app-prod-debug.apk
copy app\build\outputs\apk\prod\debug\app-prod-debug.apk <repo>\apps\nowinandroid.apk
```

`apps/` đã nằm trong `.gitignore` nên APK sẽ không bị commit.

Lưu ý applicationId: biến thể `prodDebug` có id `com.google.samples.apps.nowinandroid.debug`
(suffix `.debug`), còn `prodRelease` mới giữ đúng id `com.google.samples.apps.nowinandroid`
(nhưng release cần signing config). Driver launch app theo capability
`appium:appPackage` (field `app:` trong flow chỉ là metadata) — nên nếu build
`prodDebug`, thêm vào `config/devices.yaml`:

```yaml
android:
  capabilities:
    appPackage: com.google.samples.apps.nowinandroid.debug
```

**Phương án B — cài từ Play Store** trên emulator có Play Store (id đúng
`com.google.samples.apps.nowinandroid`); khi đó bỏ capability `app:` khỏi
`config/devices.yaml` để Appium không thử cài lại APK.

Kiểm tra nhanh asset nếu muốn xác nhận lại (kết quả hiện tại là rỗng):

```powershell
gh release view --repo android/nowinandroid --json assets --jq '.assets[].name'
```

## 5. API keys — [USER, tùy chọn nhưng khuyến nghị]

```powershell
$env:TYPESAFE_API_KEY  = "<từ https://console.typesafe.ai/keys>"
$env:ANTHROPIC_API_KEY = "<key Anthropic của bạn>"
```

(Lưu ý: CLI không có cơ chế .env loading — set trong shell sẽ chạy `uv run`.
Thiếu key thì run vẫn hoạt động: JEV content-quality và vision checks bị bỏ qua,
điểm số sẽ ít chiều hơn.)

## 6. Tuning cấu hình trước khi chạy — [USER]

- `config/devices.yaml` (mục `android`): thêm `udid: emulator-5554` (xem
  "Lưu ý quan trọng" #2). Nếu build `prodDebug`, thêm `appPackage` như mục 4.
- **Selector tuning**: mở **Appium Inspector** (GUI, https://github.com/appium/appium-inspector),
  connect tới `127.0.0.1:4723` với capabilities giống mục `android` trong
  `config/devices.yaml`, duyệt các màn Home → Topics → Settings của app thật để
  lấy selector đúng. Cập nhật:
  - `flows/login_smoke.yaml` (các `target: "acc-id:..."`)
  - `config/policy.yaml` (mục `functional_expectations`)
  Mục tiêu: cả 3 checkpoint `home` / `topics` / `settings` capture được screenshot.

## 7. Chạy

Terminal 1 — Appium server (chạy từ **repo root**, xem "Lưu ý quan trọng" #1):

```powershell
cd C:\Working\FY26\Personal\jev-agent-ui-checking
appium                                   # server tại 127.0.0.1:4723
```

Terminal 2 — chạy flow (repo root):

```powershell
uv run python -m jev_ui_agent run --flow flows/login_smoke.yaml --driver android
```

Expected:

```
Run run-<timestamp>: 3 checkpoints, N failed checks
Report: reports/run-<timestamp>/report.html
```

## 8. Troubleshooting

- `adb, emulator could not be found because ANDROID_HOME is NOT set` → làm lại
  mục 3 bước 3, mở lại terminal.
- Session tạo nhưng treo ở `Setting up Android session` → emulator chưa lên
  hẳn; đợi `adb devices` hiện `device` (không phải `offline`) rồi chạy lại.
- `Could not find a package to install` / cài APK fail → sai đường dẫn `app:`
  (xem "Lưu ý quan trọng" #1) hoặc APK build sai biến thể.
- App mở rồi nhưng tap không tìm thấy element → selector chưa đúng, làm lại mục 6.

## Lưu ý quan trọng (từ review)

1. **Đường dẫn `app:` resolve theo cwd của Appium server, không phải cwd của
   lệnh `uv run`.** `app: ./apps/nowinandroid.apk` trong `config/devices.yaml`
   chỉ hoạt động khi `appium` được khởi động từ repo root. Giải pháp thay thế:
   đổi sang đường dẫn tuyệt đối (VD `C:/Working/FY26/Personal/jev-agent-ui-checking/apps/nowinandroid.apk`).
2. **Thêm `udid: emulator-5554` vào capabilities** nếu máy có nhiều thiết bị
   nối đồng thời — trên Appium 2, `deviceName` chỉ mang tính thông tin, không
   còn dùng để chọn thiết bị.
3. **Selector phải tune theo app thật** bằng Appium Inspector (mục 6) rồi cập
   nhật `flows/login_smoke.yaml` + `config/policy.yaml`
   (`functional_expectations`); tiêu chí hoàn thành là các checkpoint
   home/topics/settings đều capture được.
