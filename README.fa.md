# Backuper

<img src="backuper_app/assets/backuper-icon.png" alt="آیکون Backuper" width="96">

بکاپ یک پوشهٔ معمولی را به‌صورت ZIP به چت خصوصی‌ات با ربات تلگرام می‌فرستد. روی macOS، ویندوز و لینوکس اجرا می‌شود. رابط گرافیکی به Python 3.11 یا جدیدتر با Tkinter نیاز دارد.

## نیازمندی‌ها

| نیازمندی | چه زمانی لازم است | لینک رسمی |
| --- | --- | --- |
| Python نسخهٔ ۳٫۱۱ یا جدیدتر همراه Tcl/Tk | اجرای برنامهٔ گرافیکی | [نصب‌کنندهٔ مک](https://www.python.org/downloads/macos/)، [نصب‌کنندهٔ ویندوز](https://www.python.org/downloads/windows/) |
| Tkinter در لینوکس | اگر نصب فعلی Python آن را ندارد | [بستهٔ Debian](https://packages.debian.org/trixie/python3-tk)، [بستهٔ Ubuntu](https://packages.ubuntu.com/search?keywords=python3-tk)، [بستهٔ Fedora](https://packages.fedoraproject.org/pkgs/python3.14/python3-tkinter/) |
| توکن ربات تلگرام | اتصال برنامه و دریافت بکاپ | [BotFather](https://t.me/BotFather) |
| curl | استفاده از پراکسی در برنامه | [دانلود curl](https://curl.se/download.html) |
| Xray-core | وارد کردن مستقیم لینک VLESS، VMess یا Trojan | [دانلود Xray-core](https://github.com/XTLS/Xray-core/releases) |

## نصب تک‌خطی

بعد از نصب Python همراه Tkinter، دستور سیستم‌عاملت را اجرا کن. دستور برنامه را از GitHub در پوشهٔ کاربرت نصب می‌کند و مسیر باز کردنش را نشان می‌دهد. دستور مک و لینوکس به curl هم نیاز دارد.

**مک و لینوکس**

```sh
(t=$(mktemp) && trap 'rm -f "$t"' 0 && curl -fsSL https://raw.githubusercontent.com/aryanmog13/backuper/main/install.py -o "$t" && python3 "$t")
```

**PowerShell ویندوز**

```powershell
& { $t = [IO.Path]::GetTempFileName(); try { Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/aryanmog13/backuper/main/install.py -OutFile $t -ErrorAction Stop; py -3 $t } finally { Remove-Item -LiteralPath $t } }
```

## رابط گرافیکی

- **macOS** — روی `Backuper.app` در Finder دوبار کلیک کن.
- **ویندوز** — بعد از نصب Python با Tcl/Tk، روی `Backuper-Windows.cmd` دوبار کلیک کن. از ترمینال هم می‌توانی با `py -3 backuper_gui.py` اجرا کنی.
- **لینوکس** — در پوشهٔ پروژه `./Backuper-Linux.sh` را اجرا کن. در Debian و Ubuntu بستهٔ Tkinter معمولاً `python3-tk` است. در Fedora بستهٔ `python3-tkinter` را نصب کن.

لانچرها را از پوشهٔ پروژه اجرا کن تا به فایل‌های پایتون کنارشان دسترسی داشته باشند.

۱. با دستور `/newbot` در [BotFather](https://t.me/BotFather) ربات بساز. توکن را در برنامه وارد کن، **Connect Bot** و سپس **Open Telegram** را بزن. در تلگرام روی **Start** بزن.

۲. با **Choose Folder** یک پوشهٔ عادی انتخاب کن. **Send ZIP** فایل را فوراً می‌فرستد. با **Listen for /backup** می‌توانی از داخل چت خصوصی ربات فرمان `/backup` بدهی. برای توقف شنیدن فرمان، **Stop** را بزن.

اگر از ترمینال اجرا می‌کنی، دستور `python3 backuper_gui.py` همان پنجره را باز می‌کند.

### بکاپ خودکار

در **Automatic backups** فاصله را بر حسب ساعت وارد کن و **Start Schedule** را بزن. پیش‌فرض ۶ ساعت است. اولین بکاپ بعد از همین فاصله شروع می‌شود. برنامه زمان بکاپ بعدی را نشان می‌دهد و **Send ZIP** در زمان انتظار هم کار می‌کند. برای دریافت فرمان تلگرام هم‌زمان با زمان‌بندی، گزینهٔ **Also listen for /backup** را فعال کن.

پنجره را باز نگه دار. اگر موعد بکاپ در زمان خواب سیستم گذشته باشد، برنامه پس از بیدارشدن یک بکاپ می‌گیرد. تنظیمات برای اجرای بعدی ذخیره می‌شوند و بعد از بازکردن دوبارهٔ برنامه باید **Start Schedule** را بزنی.

### پراکسی

در بخش **Proxy** آدرس یا لینک پراکسی را بچسبان و **Save Proxy** را بزن. برای حذف پراکسی، فیلد را خالی و دوباره ذخیره کن. فیلد برای محافظت از اطلاعات ورود مخفی نمایش داده می‌شود. برای استفاده از این بخش، `curl` باید روی سیستم در دسترس باشد.

- برای `host:port`، `host:port:user:pass` و `user:pass@host:port` نوع پراکسی را از فهرست انتخاب کن.
- برای URL کامل، نوع از خود لینک خوانده می‌شود. نمونه‌ها `http://host:8080`، `https://host:8443`، `socks4://host:1080` و `socks5h://user:pass@host:1080`. در URL کامل کاراکترهای خاص نام کاربری و رمز را URL-encode کن.
- برای `vless://`، `vmess://` و `trojan://` باید [Xray-core](https://github.com/XTLS/Xray-core/releases) هم نصب باشد و فایل اجرایی آن در PATH قرار داشته باشد. در مک مسیرهای معمول Homebrew هم بررسی می‌شوند. از TCP، WebSocket، gRPC، HTTPUpgrade و XHTTP و تنظیمات رایج TLS و REALITY پشتیبانی می‌شود. لینک VMess قدیمی با دادهٔ JSON کدشده هم پذیرفته می‌شود.
- اگر کلاینت V2Ray یا Xray از قبل روشن است، می‌توانی آدرس SOCKS محلی خودت را وارد کنی، مثلاً `socks5h://127.0.0.1:10808`. این روش برای کانفیگ‌هایی که کلاینت خودش مدیریت می‌کند هم کار می‌کند.

پراکسی برای اتصال ربات، گرفتن فرمان و آپلودهای داخل برنامه استفاده می‌شود. تنظیمات در پوشهٔ کاربر ذخیره می‌شوند. در مک و لینوکس در `~/.config/backuper/` و در ویندوز در `%LOCALAPPDATA%\Backuper\`.

## راه‌اندازی از خط فرمان

۱. در تلگرام به [BotFather](https://t.me/BotFather) پیام بده و با `/newbot` یک ربات بساز.

۲. در ترمینال، از پوشهٔ همین ابزار دستور زیر را اجرا کن. در ویندوز به‌جای `python3` از `py -3` استفاده کن. توکن را در ورودی مخفی ترمینال وارد کن، لینک چاپ‌شده را در تلگرام باز کن و Start را بزن. توکن در `telegram.json` در پوشهٔ تنظیمات کاربر ذخیره می‌شود.

```sh
python3 backuper.py setup
```

## فرستادن بکاپ

برای بکاپ فوری، مسیر واقعی پوشه را جایگزین کن.

```sh
python3 backuper.py send "/path/to/folder"
```

برای گرفتن بکاپ با فرمان تلگرام، دستور زیر را اجرا کن و در چت خصوصی ربات `/backup` بفرست. تا وقتی ترمینال باز است و سیستم بیدار و آنلاین است، ربات فرمان را می‌گیرد. با Ctrl+C متوقفش کن.

```sh
python3 backuper.py listen "/path/to/folder"
```

ZIP شامل فایل‌های عادی، فایل‌های مخفی و پوشه‌های خالی است. لینک‌های نمادین و فایل‌های ویژه کنار گذاشته می‌شوند. ZIP رمزگذاری نمی‌شود. برای بکاپی که از سقف آپلود ربات بزرگ‌تر باشد، ابزار فایل را به چند قسمت تقسیم می‌کند و پس از ارسال کامل، دستور اتصال قسمت‌ها را در تلگرام می‌فرستد. همهٔ قسمت‌ها را در یک پوشه دانلود کن، دستور را در همان پوشه اجرا کن و سپس ZIP را باز کن.
