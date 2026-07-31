<p align="right"><strong>Türkçe</strong> | <a href="./README.en.md">English</a></p>

# Monster Fan Reset

Uyumlu Monster / Tongfang dizüstülerde fanı uyku moduna girmeden kısa süre durdurup yeniden başlatmak için deneysel, açık kaynak Windows aracı.

Araç, üretici yazılımının kendi WMI fan metotlarını kullanır ve işlem bittiğinde fanları **mutlaka firmware’in otomatik kontrolüne** geri verir. Başlangıç amacı, zaman zaman oluşan mekanik fan gıcırtısını fanı yeniden başlatarak gidermektir.

> [!WARNING]
> Bu araç donanıma özgü ve deneyseldir. Sadece **Monster Abra A5 V21.1 (Tongfang GM5MU)** üzerinde doğrulanmıştır. Boşta ve serin bir bilgisayarda, sıcaklığı takip ederek kullanın. Oyun, render, yoğun şarj veya yüksek sıcaklık altında kullanmayın.

## Neler yapar?

- **CPU**: CPU fanını kısa süre durdurur; GPU fanını tam hızda açık tutar.
- **GPU**: GPU fanını kısa süre durdurur; CPU fanını tam hızda açık tutar.
- **Both**: İki ana fanı kısa süre durdurur.
- İşlem öncesinde ve işlem boyunca EC sıcaklığını okur.
- Sıcaklık sınırına ulaşılırsa işlemi erken sonlandırır.
- Hata olsa bile tüm fanları firmware’in otomatik moduna döndürür.

## Gereksinimler

1. Windows 10/11, PowerShell ve yönetici yetkisi.
2. `python` komutuyla erişilebilen Python 3.
3. [PawnIO 2.2.0](https://github.com/namazso/PawnIO.Setup/releases/tag/2.2.0).
4. [PawnIO.Modules](https://github.com/namazso/PawnIO.Modules/releases) içindeki `LpcACPIEC.bin` dosyası. Dosyayı `src/ec.py` yanına koyun; bu dosya depoya dahil değildir ve kendi lisansına tabidir.

## Kurulum

```powershell
git clone https://github.com/alitura1/monster-fan-reset.git
cd monster-fan-reset\src
Copy-Item FanReset.ini.example FanReset.ini
```

Yönetici olarak açılmış PowerShell’de:

```powershell
.\FanReset.ps1 -TargetFan CPU
.\FanReset.ps1 -TargetFan GPU
.\FanReset.ps1 -TargetFan Both
```

Tıklanabilir başlatıcı için AutoHotkey v2 kurup `FanReset.ahk` dosyasını çalıştırabilirsiniz. Derlenmiş `.exe` dosyası bilerek dağıtılmaz.

## Ayarlar

`src/FanReset.ini.example` dosyasını `FanReset.ini` olarak kopyaladıktan sonra düzenleyin:

- `HoldSeconds`: 1–10 saniye, varsayılan `4`.
- `TempAbort`: 60–95 °C, varsayılan `85`.
- `TargetFan`: Komut satırında hedef verilmezse `CPU`, `GPU` veya `Both`.

Herkese açık sürümde süresiz fan kapatma ve 10 saniyeyi aşan çalışma süresi bilerek yoktur.

## Tek fan manuel kapatma modu

`FanManual.ps1`, sorun giderme için bir ana fanı manuel olarak kapatmayı sağlar. Aynı anda yalnızca **tek** ana fan kapalı kalabilir:

```powershell
.\FanManual.ps1 -Action CPUOff  # CPU fanı kapalı, GPU fanı %100 açık
.\FanManual.ps1 -Action GPUOff  # CPU yeniden açılır, GPU fanı kapanır
.\FanManual.ps1 -Action Auto    # Tüm fanlar otomatik moda döner
```

Arka plan izleyicisi EC sıcaklığını saniyede iki kez denetler. Sıcaklık okunamazsa veya `TempAbort` sınırına ulaşılırsa tüm fanlar otomatik moda döner. CPU kapalıyken GPU’yu kapatmak isterseniz önce CPU otomatiğe geri döner, sonra GPU kapanır; iki ana fanın aynı anda kapalı kalmasına izin verilmez.

Bu mod, normal soğutmanın yerine geçmez. Bilgisayar yük altındayken kullanmayın.

## Fan eşlemesi

Doğrulanan cihazda firmware duty baytı 0 = CPU fanı, duty baytı 1 = GPU fanıdır. Bu eşleme başka Tongfang modellerinde farklı olabilir. Yanlış fan etkilenirse test etmeyi bırakıp issue açın.

## Uyumluluk ve katkı

Uyumluluk tablosu için [docs/compatibility.md](./docs/compatibility.md) dosyasına bakın. Hata raporları, model uyumluluk raporları, dokümantasyon iyileştirmeleri ve daha güvenli sensör yöntemleri memnuniyetle karşılanır.

Issue’lara seri numarası, Windows kullanıcı adı veya tam yerel dosya yolu içeren loglar koymayın.

## Lisans

MIT. Üçüncü taraf bağımlılıklar kendi lisanslarını korur.
