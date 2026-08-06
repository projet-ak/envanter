#!/usr/bin/env bash
# .env dosyasını DEĞERLERİ GİZLEYEREK denetler.
# Kullanım:  bash scripts/env-kontrol.sh [dosya]
DOSYA="${1:-.env}"
[[ -f "$DOSYA" ]] || { echo "✗ Dosya yok: $DOSYA"; exit 1; }

echo "=== $DOSYA (değerler gizli) ==="
awk '
{
  if ($0 ~ /^[[:space:]]*$/) { printf "%2d: (boş)\n", NR; next }
  if ($0 ~ /^[[:space:]]*#/) { printf "%2d: # yorum\n", NR; next }
  n = index($0, "=")
  if (n > 1 && substr($0,1,n-1) ~ /^[A-Za-z_][A-Za-z0-9_]*$/) {
    printf "%2d: %-26s = *** (%d karakter)\n", NR, substr($0,1,n-1), length($0)-n
  } else {
    printf "%2d: >>> GEÇERSİZ SATIR <<< : %.60s\n", NR, $0
    hata = 1
  }
}
END {
  if (hata) {
    print ""
    print "⚠ Geçersiz satırlar python-dotenv tarafından atlanır ve ayarlar yüklenmez."
    print "  Bu satırları sil:  nano " ARGV[1]
  } else {
    print ""
    print "✓ Tüm satırlar geçerli"
  }
}' "$DOSYA"

echo ""
echo "=== Kritik ayarlar ==="
for anahtar in DATABASE_URL SECRET_KEY ROOT_PATH ORG_NAME SNIPEIT_URL SNIPEIT_TOKEN ANTHROPIC_API_KEY; do
    deger="$(grep -E "^${anahtar}=" "$DOSYA" | head -1 | cut -d= -f2-)"
    if [[ -z "$deger" ]]; then
        printf "  %-20s \033[33meksik/boş\033[0m\n" "$anahtar"
    elif [[ "$anahtar" == *TOKEN* || "$anahtar" == *KEY* || "$anahtar" == *SECRET* ]]; then
        printf "  %-20s \033[32mvar\033[0m (%d karakter)\n" "$anahtar" "${#deger}"
    else
        printf "  %-20s %s\n" "$anahtar" "$deger"
    fi
done
