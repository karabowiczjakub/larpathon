# Konfiguracja i Uruchomienie Projektu

Ten projekt wymaga zainstalowanego języka Python. Aby uniknąć konfliktów z innymi pakietami w systemie, zaleca się uruchamianie go w izolowanym środowisku wirtualnym (`.venv`).

## Linux / macOS

1. **Otwórz terminal** i przejdź do folderu głównego projektu.
2. **Utwórz środowisko wirtualne** o nazwie `.venv`:
   ```bash
   python3 -m venv .venv
   ```
3. **Aktywuj środowisko wirtualne**:
   ```bash
   source .venv/bin/activate
   ```
   *(Po poprawnej aktywacji, na początku linii w terminalu powinien pojawić się napis `(.venv)`).*
4. **Zainstaluj wymagane pakiety** z pliku `requirements.txt`:
   ```bash
   pip install -r requirements.txt
   ```

## Windows

1. **Otwórz wiersz poleceń (CMD) lub PowerShell** i przejdź do folderu głównego projektu.
2. **Utwórz środowisko wirtualne** o nazwie `.venv`:
   ```cmd
   python -m venv .venv
   ```
3. **Aktywuj środowisko wirtualne**:
   ```cmd
   .venv\Scripts\activate
   ```
   *(Po poprawnej aktywacji, na początku wiersza poleceń powinien pojawić się napis `(.venv)`).*
4. **Zainstaluj wymagane pakiety** z pliku `requirements.txt`:
   ```cmd
   pip install -r requirements.txt
   ```

---

## 🚀 Uruchomienie Aplikacji

Gdy środowisko jest **aktywne** i wszystkie pakiety zostały zainstalowane, możesz uruchomić aplikację wpisując polecenie:

```bash
streamlit run app.py
```
*(Zwróć uwagę, aby znajdować się w odpowiednim folderze, lub podaj właściwą ścieżkę do pliku `app.py`).*

**Zakończenie pracy:**
Aby wyjść ze środowiska wirtualnego, wystarczy wpisać w terminalu komendę: `deactivate`.