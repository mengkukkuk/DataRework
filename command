# Build the executable

.venv/Scripts/python.exe -m PyInstaller DataRework.spec --noconfirm

cp "G:/Code/DataRework/.env" "G:/Code/DataRework/dist/.env"

python.exe ".venv\Scripts\pywin32_postinstall.py" -install

