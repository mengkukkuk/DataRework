"""The manual's text, in English and Thai, built from one source.

Every on-screen label is looked up in LABELS so the manual quotes exactly what
the app shows in that language (taken from locales/en.json and locales/th.json).
A few app strings were never translated (the Report damage tab, the card pager);
the Thai edition quotes them in English because that is what Thai users see.
"""
from manual_lib import CSS, bullets, callout, esc, figure, steps, table

# key: (English label, Thai label) -- exactly as the app displays them.
LABELS = {
    "records": ("Records", "รายการข้อมูล"),
    "containers": ("Container manager", "จัดการบรรจุภัณฑ์"),
    "damage": ("Report damage", "Report damage"),
    "filters": ("Filters", "ตัวกรอง"),
    "day": ("Day", "วันที่"), "month": ("Month", "เดือน"), "year": ("Year", "ปี"),
    "product": ("Product name", "ชื่อผลิตภัณฑ์"),
    "job": ("Ass. job no.", "เลขที่ใบสั่งงาน"),
    "category": ("Category", "ระดับบรรจุภัณฑ์"),
    "tag": ("Tag", "พารามิเตอร์"),
    "value": ("Value", "ค่า"),
    "search": ("Search", "ค้นหา"), "clear": ("Clear", "ล้าง"),
    "columns": ("Columns", "คอลัมน์"),
    "hide_filters": ("Hide filters", "ซ่อนตัวกรอง"), "show_filters": ("Show filters", "แสดงตัวกรอง"),
    "save": ("Save", "บันทึก"), "cancel": ("Cancel", "ยกเลิก"),
    "delete": ("Delete", "ลบ"), "del": ("Del", "ลบ"),
    "log": ("Log", "ล็อก"),
    "rename_c": ("Rename container…", "เปลี่ยนรหัสบรรจุภัณฑ์…"),
    "delete_c": ("Delete container…", "ลบบรรจุภัณฑ์…"),
    "refresh": ("Refresh", "รีเฟรช"),
    "find_level": ("Find serial in this level", "ค้นหารหัสในระดับนี้"),
    "open_box": ("Open box", "เปิดกล่อง"), "view_records": ("View records", "ดูข้อมูล"),
    "rename": ("Rename", "เปลี่ยนรหัส"),
    "show_all": ("Show all", "แสดงทั้งหมด"), "show_all_records": ("Show all records", "แสดงข้อมูลทั้งหมด"),
    "apply": ("Apply", "นำไปใช้"), "skip": ("Skip", "ข้าม"),
    "select_all": ("Select all", "เลือกทั้งหมด"), "select_none": ("Select none", "ยกเลิกการเลือกทั้งหมด"),
    "close": ("Close", "ปิด"), "copy": ("Copy", "คัดลอก"),
    "dark": ("Dark", "มืด"), "light": ("Light", "สว่าง"),
    "level": ("Level", "ระดับ"), "serial": ("Serial", "รหัสซีเรียล"),
    "login": ("Login", "เข้าสู่ระบบ"), "username": ("Username", "ชื่อผู้ใช้"), "password": ("Password", "รหัสผ่าน"),
    "show_password": ("Show password", "แสดงรหัสผ่าน"),
    "prev": ("← Previous", "← Previous"), "next": ("Next →", "Next →"),
    "all_cartons": ("All cartons", "ลังทั้งหมด"), "unassigned": ("Unassigned", "ยังไม่ระบุ"),
    "unit": ("Unit", "หน่วยสินค้า"), "inner": ("Inner", "กล่องชั้นใน"),
    "display": ("Display", "กล่องแสดงสินค้า"), "carton": ("Carton", "ลัง"),
    "serial_no": ("Serial No", "รหัสซีเรียล"), "roll_no": ("Roll No", "หมายเลขม้วน"),
    "source_id": ("Source ID", "รหัสต้นทาง"), "target_id": ("Target ID", "รหัสปลายทาง"),
    "admin": ("admin", "ผู้ดูแลระบบ"), "super_admin": ("super admin", "ผู้ดูแลระบบสูงสุด"), "user": ("user", "ผู้ใช้"),
    "error_log": ("Error log", "บันทึกข้อผิดพลาด"),
    "rename_children": ("Rename children", "เปลี่ยนรหัสรายการภายใน"),
}

BUILD_INFO = "commit 9c4cb78 · 2026-10-19"


def build(lang):
    th = lang == "th"
    idx = 1 if th else 0

    def t(en, th_text):
        return th_text if th else en

    def U(key):
        return f'<span class="ui">{esc(LABELS[key][idx])}</span>'

    def B(key, cls=""):
        return f'<span class="btn {cls}">{esc(LABELS[key][idx])}</span>'

    def TAB(key):
        return f'<span class="tab">{esc(LABELS[key][idx])}</span>'

    def M(text):
        return f'<span class="msg">{esc(text)}</span>'

    def lvl(key):
        return LABELS[key][idx]

    chapters = []

    def chapter(cid, title_en, title_th, body, pagebreak=True):
        chapters.append((cid, t(title_en, title_th), body, pagebreak))

    # ------------------------------------------------------------------ 1
    chapter("about", "What DataRework does", "DataRework ใช้ทำอะไร", f"""
<p>{t("DataRework (the window is titled <b>Production Rework</b>) is the desktop tool used to correct production packaging records after the fact. Every finished product <b>unit</b> is recorded together with the serial numbers of the <b>display box</b>, <b>inner box</b> and <b>carton</b> it was packed into. When a label was scanned wrongly, a unit sits in the wrong box, or a box is damaged, an authorised operator uses DataRework to find the records, correct them, and keep the serial inventory consistent.",
        "DataRework (หน้าต่างโปรแกรมใช้ชื่อ <b>Production Rework</b>) คือโปรแกรมเดสก์ท็อปสำหรับแก้ไขข้อมูลการบรรจุสินค้าในสายการผลิตย้อนหลัง สินค้าแต่ละ<b>หน่วย</b>จะถูกบันทึกพร้อมรหัสซีเรียลของ<b>กล่องแสดงสินค้า</b> <b>กล่องชั้นใน</b> และ<b>ลัง</b>ที่บรรจุอยู่ เมื่อสแกนฉลากผิด หน่วยสินค้าอยู่ผิดกล่อง หรือกล่องเสียหาย ผู้ที่ได้รับอนุญาตสามารถใช้ DataRework ค้นหา แก้ไขข้อมูล และดูแลให้คลังรหัสซีเรียลถูกต้องตรงกัน")}</p>

<h3>{t("How products are packed", "โครงสร้างการบรรจุ")}</h3>
<div class="chain">
  <span class="lvl carton">{lvl("carton")}</span><span class="arrow">{t("contains", "บรรจุ")} →</span>
  <span class="lvl inner">{lvl("inner")}</span><span class="arrow">{t("contains", "บรรจุ")} →</span>
  <span class="lvl display">{lvl("display")}</span><span class="arrow">{t("contains", "บรรจุ")} →</span>
  <span class="lvl unit">{lvl("unit")}</span>
</div>
<p>{t("The first three levels are called <b>containers</b> because they hold other things. A unit is the smallest item and holds nothing.",
    "สามระดับแรกเรียกว่า<b>บรรจุภัณฑ์</b> เพราะบรรจุสิ่งอื่นไว้ภายใน ส่วนหน่วยสินค้าเป็นรายการที่เล็กที่สุดและไม่ได้บรรจุสิ่งใดต่อ")}</p>

<h3>{t("Words used in this manual", "คำศัพท์ที่ใช้ในคู่มือนี้")}</h3>
{table([t("Term", "คำศัพท์"), t("Meaning", "ความหมาย")], [
    [f"<b>{t('Serial / Serial No', 'รหัสซีเรียล')}</b>", t("The unique code printed on a label. Units, displays, inners and cartons each have one.", "รหัสเฉพาะที่พิมพ์บนฉลาก หน่วยสินค้า กล่องแสดงสินค้า กล่องชั้นใน และลัง ต่างมีรหัสของตัวเอง")],
    [f"<b>{t('Roll No', 'หมายเลขม้วน')}</b>", t("The label roll a serial was printed from. It follows the serial automatically when a serial is changed.", "ม้วนฉลากที่ใช้พิมพ์รหัสซีเรียลนั้น ระบบจะเปลี่ยนตามรหัสซีเรียลให้อัตโนมัติเมื่อมีการเปลี่ยนรหัส")],
    [f"<b>{t('Record (row)', 'ข้อมูล (แถว)')}</b>", t("One saved line for one unit, carrying the serials of every container it sits in.", "ข้อมูลหนึ่งบรรทัดของหน่วยสินค้าหนึ่งหน่วย พร้อมรหัสของบรรจุภัณฑ์ทุกระดับที่หน่วยนั้นอยู่")],
    [f"<b>{t('Link', 'การเชื่อมโยง')}</b>", t("The saved connection between an item and the container directly above it.", "ความสัมพันธ์ที่บันทึกไว้ระหว่างรายการหนึ่งกับบรรจุภัณฑ์ที่อยู่เหนือขึ้นไปหนึ่งระดับ")],
    [f"<b>{t('In use / Free', 'ใช้งานอยู่ / ว่าง')}</b>", t("Every serial in the serial inventory is either <i>in use</i> (attached to something in production) or <i>free</i>. Fixing records moves serials between the two states.", "รหัสซีเรียลทุกตัวในคลังรหัสจะอยู่ในสถานะ<i>ใช้งานอยู่</i> (ผูกกับสินค้าในสายการผลิต) หรือ<i>ว่าง</i> การแก้ไขข้อมูลจะย้ายรหัสระหว่างสองสถานะนี้")],
    [f"<b>{t('Damaged', 'เสียหาย')}</b>", t("A free serial that has been flagged as unusable (see Report damage).", "รหัสซีเรียลที่ว่างและถูกทำเครื่องหมายว่าใช้งานไม่ได้ (ดูหัวข้อ Report damage)")],
])}
""")

    # ------------------------------------------------------------------ 2
    chapter("start", "Before you start", "ก่อนเริ่มใช้งาน", f"""
<h3>{t("The program files", "ไฟล์ของโปรแกรม")}</h3>
<p>{t("DataRework is delivered as a folder. Keep these three files together; copy the whole folder when moving to another computer.",
      "DataRework ส่งมอบเป็นโฟลเดอร์ ให้เก็บไฟล์ทั้งสามนี้ไว้ด้วยกัน และคัดลอกทั้งโฟลเดอร์เมื่อย้ายไปเครื่องอื่น")}</p>
{table([t("File", "ไฟล์"), t("Purpose", "หน้าที่")], [
    ["<code>DataRework.exe</code>", t("The application you open and work in.", "โปรแกรมที่คุณเปิดใช้งาน")],
    ["<code>SerialStoreSync.exe</code>", t("A background program that keeps the serial usage counts up to date (see below). You never open it yourself.", "โปรแกรมทำงานเบื้องหลังที่ปรับจำนวนการใช้รหัสซีเรียลให้เป็นปัจจุบัน (ดูด้านล่าง) ไม่ต้องเปิดเอง")],
    ["<code>nssm.exe</code>", t("The helper that installs the background program as a Windows service.", "ตัวช่วยติดตั้งโปรแกรมเบื้องหลังเป็นบริการ (service) ของ Windows")],
])}

<h3>{t("The background sync service", "บริการซิงก์เบื้องหลัง")}</h3>
<p>{t("The first time DataRework opens on a computer, Windows shows a <b>User Account Control (UAC)</b> prompt. It is asking permission to install the <b>DataRework Serial Store Sync</b> service. Choose <b>Yes</b> (an administrator password may be requested).",
      "เมื่อเปิด DataRework ครั้งแรกบนเครื่อง Windows จะแสดงหน้าต่าง <b>User Account Control (UAC)</b> เพื่อขออนุญาตติดตั้งบริการ <b>DataRework Serial Store Sync</b> ให้เลือก <b>Yes</b> (อาจต้องใส่รหัสผ่านผู้ดูแลเครื่อง)")}</p>
{bullets([
    t("The service starts automatically with Windows and keeps running after you close DataRework.", "บริการจะเริ่มทำงานพร้อม Windows และทำงานต่อแม้ปิด DataRework แล้ว"),
    t("About every <b>10 seconds</b> it recounts how many serials are <i>in use</i> and <i>damaged</i> for each roll. After you save a change, those totals can lag by about 10 seconds.", "ทุกประมาณ <b>10 วินาที</b> บริการจะนับจำนวนรหัสที่<i>ใช้งานอยู่</i>และ<i>เสียหาย</i>ของแต่ละม้วนใหม่ ดังนั้นหลังบันทึก ยอดรวมอาจล่าช้าได้ประมาณ 10 วินาที"),
    t("If you decline the prompt DataRework still works, but the totals will not update until the service is installed. The prompt appears again the next time you start the program.", "หากไม่อนุญาต DataRework ยังใช้งานได้ แต่ยอดรวมจะไม่อัปเดตจนกว่าจะติดตั้งบริการ และจะถามอีกครั้งเมื่อเปิดโปรแกรมครั้งต่อไป"),
])}

<h3>{t("Who can do what", "ใครทำอะไรได้บ้าง")}</h3>
<p>{t("What you can change depends on the <b>role</b> of your account. Your role is shown next to your name at the top right of the window.",
      "สิ่งที่คุณแก้ไขได้ขึ้นกับ<b>บทบาท (role)</b> ของบัญชี ซึ่งแสดงอยู่ถัดจากชื่อของคุณที่มุมขวาบนของหน้าต่าง")}</p>
{table([t("Role", "บทบาท"), t("Can do", "ทำได้"), t("Cannot do", "ทำไม่ได้")], [
    [f"<b>admin</b> / <b>super admin</b><br><small>{lvl('admin') if th else ''}{' / ' if th else ''}{lvl('super_admin') if th else ''}</small>",
     t("Everything: search, browse, edit cells, delete rows, Save, rename containers, delete containers, report damage. <i>super admin</i> has exactly the same power as <i>admin</i>.", "ทุกอย่าง: ค้นหา เรียกดู แก้ไขเซลล์ ลบแถว บันทึก เปลี่ยนรหัสบรรจุภัณฑ์ ลบบรรจุภัณฑ์ และ Report damage โดย <i>super admin</i> มีสิทธิ์เท่ากับ <i>admin</i> ทุกประการ"),
     "—"],
    [t("any other role (for example <b>user</b>)", "บทบาทอื่น (เช่น <b>ผู้ใช้</b>)"),
     t("Search, filter, browse containers, view records, <b>Report damage</b>.", "ค้นหา กรองข้อมูล เรียกดูบรรจุภัณฑ์ ดูข้อมูล และ <b>Report damage</b>"),
     t("Edit cells, delete rows, Save, rename or delete containers. These buttons are greyed out and show a tooltip such as “Only admins can save changes”.", "แก้ไขเซลล์ ลบแถว บันทึก เปลี่ยนรหัสหรือลบบรรจุภัณฑ์ ปุ่มเหล่านี้จะเป็นสีเทาและมีคำอธิบายเมื่อชี้เมาส์ เช่น “เฉพาะผู้ดูแลระบบเท่านั้นที่บันทึกการเปลี่ยนแปลงได้”")],
])}
{callout("warn", t("Report damage is open to every role", "Report damage ใช้ได้ทุกบทบาท"), f"<p>{t('The Report damage tab has no administrator check. Anyone who can sign in can flag a serial as damaged, and the app has no undo for it.', 'แท็บ Report damage ไม่ตรวจสอบสิทธิ์ผู้ดูแลระบบ ทุกคนที่เข้าสู่ระบบได้สามารถทำเครื่องหมายรหัสว่าเสียหายได้ และโปรแกรมไม่มีปุ่มย้อนกลับ')}</p>")}

<h3>{t("Barcode scanners", "เครื่องสแกนบาร์โค้ด")}</h3>
<p>{t("Keyboard-style scanners type the code and then press <kbd>Enter</kbd>. DataRework is built for this: in the <b>Value</b> box <kbd>Enter</kbd> runs the search; in the Rename and Delete dialogs <kbd>Enter</kbd> only <i>looks the serial up</i> and never confirms anything; in <b>Report damage</b> <kbd>Enter</kbd> submits the report straight away.",
      "เครื่องสแกนแบบคีย์บอร์ดจะพิมพ์รหัสแล้วกด <kbd>Enter</kbd> ให้เอง DataRework ออกแบบให้รองรับการทำงานนี้: ในช่อง<b>ค่า</b> <kbd>Enter</kbd> จะค้นหาทันที ในหน้าต่างเปลี่ยนรหัสและลบ <kbd>Enter</kbd> เพียง<i>ค้นหารหัส</i>และไม่ยืนยันการทำรายการใด ๆ ส่วนใน <b>Report damage</b> <kbd>Enter</kbd> จะส่งรายงานทันที")}</p>

<h3>{t("Remembered settings", "การตั้งค่าที่โปรแกรมจำไว้")}</h3>
<p>{t("DataRework remembers, per Windows user: the language (EN / TH), the colour theme (Dark / Light), and whether the filter panel is folded on each tab.",
      "DataRework จำค่าต่อไปนี้ไว้สำหรับผู้ใช้ Windows แต่ละคน: ภาษา (EN / TH) ธีมสี (มืด / สว่าง) และสถานะการพับตัวกรองในแต่ละแท็บ")}</p>
""")

    # ------------------------------------------------------------------ 3
    chapter("login", "Signing in", "การเข้าสู่ระบบ", f"""
{figure("login_%s.png" % lang, t("The sign-in window.", "หน้าต่างเข้าสู่ระบบ"), narrow=True)}
{steps([
    t(f"Open <code>DataRework.exe</code>. The sign-in window appears.", "เปิด <code>DataRework.exe</code> หน้าต่างเข้าสู่ระบบจะปรากฏขึ้น"),
    t(f"Type your {U('username')} and {U('password')}. Tick {U('show_password')} to check what you typed.", f"พิมพ์{U('username')}และ{U('password')} ติ๊ก {U('show_password')} หากต้องการตรวจสอบสิ่งที่พิมพ์"),
    t(f"Press <kbd>Enter</kbd> or click {B('login', 'blue')}.", f"กด <kbd>Enter</kbd> หรือคลิก {B('login', 'blue')}"),
    t("The main window opens and the sign-in window closes.", "หน้าต่างหลักจะเปิดขึ้น และหน้าต่างเข้าสู่ระบบจะปิดลง"),
])}
<p>{t("You can switch the language with the <b>EN / TH</b> buttons at the top right of the sign-in window.", "สามารถสลับภาษาได้ด้วยปุ่ม <b>EN / TH</b> ที่มุมขวาบนของหน้าต่างเข้าสู่ระบบ")}</p>
<h3>{t("If sign-in fails", "หากเข้าสู่ระบบไม่ได้")}</h3>
{table([t("Message", "ข้อความ"), t("What it means and what to do", "ความหมายและสิ่งที่ควรทำ")], [
    [M(t("Invalid username or password", "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")), t("The password is wrong. The password box is cleared; type it again.", "รหัสผ่านไม่ถูกต้อง ช่องรหัสผ่านจะถูกล้าง ให้พิมพ์ใหม่อีกครั้ง")],
    [M(t("This user does not have permission to Log in", "User นี้ไม่สามารถ Log in ได้")), t("Your account has been deactivated. Ask your administrator.", "บัญชีของคุณถูกปิดการใช้งาน โปรดติดต่อผู้ดูแลระบบ")],
    [M(t("This user does not have permission to rework", "User นี้ไม่สามารถใช้งาน rework ได้")), t("Your account is not allowed to use this application. Ask your administrator to enable rework access.", "บัญชีของคุณยังไม่ได้รับสิทธิ์ใช้โปรแกรมนี้ โปรดขอให้ผู้ดูแลระบบเปิดสิทธิ์ rework")],
    [M(t("Unable to reach the database", "ไม่สามารถเชื่อมต่อฐานข้อมูลได้")), t("The computer cannot reach the company database (network, VPN or server problem). Check the connection and try again; if it persists, contact IT.", "เครื่องของคุณเชื่อมต่อฐานข้อมูลของบริษัทไม่ได้ (ปัญหาเครือข่าย VPN หรือเซิร์ฟเวอร์) ตรวจสอบการเชื่อมต่อแล้วลองใหม่ หากยังไม่ได้ให้ติดต่อฝ่าย IT")],
    [t("Nothing happens", "ไม่มีอะไรเกิดขึ้น"), t("If the username you typed does not exist the window may simply not respond. Re-check the spelling of the username.", "หากชื่อผู้ใช้ที่พิมพ์ไม่มีอยู่ในระบบ หน้าต่างอาจไม่ตอบสนองและไม่แสดงข้อความ ให้ตรวจสอบการสะกดชื่อผู้ใช้อีกครั้ง")],
])}
""")

    # ------------------------------------------------------------------ 4
    marks = [(1, 1058, 18), (2, 1124, 18), (3, 20, 72), (4, 20, 233), (5, 22, 286),
             (6, 22, 350), (7, 12, 702), (8, 138, 702), (9, 702, 702), (10, 876, 702), (11, 1036, 702),
             (12, 1124, 702), (13, 1206, 702)]
    chapter("tour", "A tour of the main window", "ทำความรู้จักหน้าต่างหลัก", f"""
{figure("records_%s.png" % lang, t("The main window on the Records tab. Numbers are explained below.", "หน้าต่างหลักที่แท็บ รายการข้อมูล ตัวเลขอธิบายอยู่ด้านล่าง"), marks=marks)}
{table(["#", t("Part", "ส่วน"), t("What it does", "หน้าที่")], [
    ["1", t("Settings", "การตั้งค่า"), t("The gear button opens the settings window: language (English / ไทย) and colour theme (Dark / Light).", "ปุ่มรูปเฟืองเปิดหน้าต่างการตั้งค่า: ภาษา (English / ไทย) และธีมสี (มืด / สว่าง)")],
    ["2", t("Signed-in user", "ผู้ใช้ที่เข้าสู่ระบบ"), t("Your username and role.", "ชื่อผู้ใช้และบทบาทของคุณ")],
    ["3", U("filters"), t("Chooses which records to load. Applies to the Records and Container manager tabs.", "เลือกข้อมูลที่ต้องการโหลด ใช้กับแท็บรายการข้อมูลและแท็บจัดการบรรจุภัณฑ์")],
    ["4", t("Tabs", "แท็บ"), t(f"{TAB('records')}, {TAB('containers')} and {TAB('damage')}.", f"{TAB('records')} {TAB('containers')} และ {TAB('damage')}")],
    ["5", U("columns"), t("Tick or untick to show or hide grid columns.", "ติ๊กหรือเอาออกเพื่อแสดงหรือซ่อนคอลัมน์ในตาราง")],
    ["6", t("Record grid", "ตารางข้อมูล"), t("One row per unit. Click a header to sort, double-click a cell to edit (admins).", "หนึ่งแถวต่อหนึ่งหน่วยสินค้า คลิกหัวคอลัมน์เพื่อจัดเรียง ดับเบิลคลิกเซลล์เพื่อแก้ไข (ผู้ดูแลระบบ)")],
    ["7", t("Status line", "บรรทัดสถานะ"), t("The latest result, in green (OK) or red (error).", "ผลลัพธ์ล่าสุด สีเขียว (สำเร็จ) หรือสีแดง (ผิดพลาด)")],
    ["8", B("log", "light"), t("Opens the error log with full details.", "เปิดบันทึกข้อผิดพลาดแบบละเอียด")],
    ["9", B("rename_c"), t("Rename a container (admins).", "เปลี่ยนรหัสบรรจุภัณฑ์ (ผู้ดูแลระบบ)")],
    ["10", B("delete_c"), t("Delete a container with everything inside (admins).", "ลบบรรจุภัณฑ์พร้อมทุกอย่างที่อยู่ภายใน (ผู้ดูแลระบบ)")],
    ["11", B("delete", "light"), t("Marks the selected rows for deletion. Visible on the Records tab only.", "ทำเครื่องหมายลบแถวที่เลือก แสดงเฉพาะแท็บรายการข้อมูล")],
    ["12", B("save", "green"), t("Writes pending edits and deletions to the database after you confirm (admins).", "บันทึกการแก้ไขและการลบที่ค้างอยู่ลงฐานข้อมูลหลังยืนยัน (ผู้ดูแลระบบ)")],
    ["13", B("cancel", "red"), t("Clears the filters and empties the grid, discarding unsaved edits.", "ล้างตัวกรองและเคลียร์ตาราง พร้อมทิ้งการแก้ไขที่ยังไม่บันทึก")],
])}
<h3>{t("Language and theme", "ภาษาและธีมสี")}</h3>
<p>{t("Click the gear button at the top right to open <b>Settings</b>. Pick a language and a colour theme; each choice takes effect immediately and is remembered the next time you open DataRework. Click <b>Close</b> when done.", "คลิกปุ่มรูปเฟืองที่มุมขวาบนเพื่อเปิด<b>การตั้งค่า</b> เลือกภาษาและธีมสี แต่ละตัวเลือกมีผลทันทีและโปรแกรมจะจำไว้ในครั้งถัดไป คลิก<b>ปิด</b>เมื่อเสร็จ")}</p>
{figure("settings_%s.png" % lang, t("The settings window.", "หน้าต่างการตั้งค่า"), narrow=True)}
{callout("note", t("A few texts are always in English", "ข้อความบางส่วนเป็นภาษาอังกฤษเสมอ"), f"<p>{t('The Report damage tab, the <b>← Previous</b> / <b>Next →</b> card pager and the “Loading…” text have no Thai translation yet, so they stay in English even when TH is selected.', 'แท็บ Report damage ปุ่มเลื่อนหน้า <b>← Previous</b> / <b>Next →</b> ของการ์ด และข้อความ “Loading…” ยังไม่มีคำแปลภาษาไทย จึงแสดงเป็นภาษาอังกฤษแม้เลือก TH')}</p>")}
{figure("readonly_%s.png" % lang, t("What a non-admin sees: the Del column is gone and Save, Rename container and Delete container are greyed out.", "สิ่งที่ผู้ใช้ที่ไม่ใช่ผู้ดูแลระบบเห็น: ไม่มีคอลัมน์ ลบ และปุ่มบันทึก เปลี่ยนรหัสบรรจุภัณฑ์ ลบบรรจุภัณฑ์ เป็นสีเทา"))}
""")

    # ------------------------------------------------------------------ 5
    chapter("filters", "Filters", "ตัวกรอง", f"""
<p>{t("The filter panel decides which records are loaded. It sits above the tabs and is shared by the <b>Records</b> and <b>Container manager</b> tabs. It is applied when you click " + B('search', 'blue') + " (or press <kbd>Enter</kbd> in the Value box).",
      "แผงตัวกรองกำหนดว่าจะโหลดข้อมูลใดบ้าง อยู่เหนือแท็บและใช้ร่วมกันระหว่างแท็บ<b>รายการข้อมูล</b>และ<b>จัดการบรรจุภัณฑ์</b> ตัวกรองจะทำงานเมื่อคลิก " + B('search', 'blue') + " (หรือกด <kbd>Enter</kbd> ในช่องค่า)")}</p>

<h3>{t("Date: Day, Month, Year", "วันที่: วันที่ เดือน ปี")}</h3>
<ul>
<li>{t("<b>Month</b> and <b>Year</b> start on <b>today’s</b> month and year, so you see this month’s records first. The Year list runs from last year to four years ahead.", "<b>เดือน</b>และ<b>ปี</b>จะเริ่มต้นที่เดือนและปีของ<b>วันนี้</b> จึงเห็นข้อมูลของเดือนปัจจุบันก่อน รายการปีเริ่มจากปีที่แล้วไปถึงอีกสี่ปีข้างหน้า")}</li>
<li>{t("Leave <b>Day</b> on its placeholder to include every day. The day list shortens to the days the chosen month really has (February never offers a 30th).", "เว้น<b>วันที่</b>ไว้ที่ค่าเริ่มต้นเพื่อรวมทุกวัน รายการวันจะปรับตามจำนวนวันจริงของเดือนที่เลือก (กุมภาพันธ์จะไม่มีวันที่ 30)")}</li>
<li>{t("Select the first entry (“Month” / “Year”) to drop that part of the date filter.", "เลือกรายการแรก (“เดือน” / “ปี”) เพื่อยกเลิกเงื่อนไขส่วนนั้นของวันที่")}</li>
</ul>
{callout("warn", t("“My records are missing” — check the date first", "“ข้อมูลหาย” — ให้ตรวจวันที่ก่อน"), f"<p>{t('Because Month and Year default to today, records created in other months do not appear until you change them. This is the most common reason a search looks empty. The date is <b>not</b> reset by ' + B('clear') + '.', 'เพราะเดือนและปีตั้งต้นเป็นวันนี้ ข้อมูลที่สร้างในเดือนอื่นจึงไม่แสดงจนกว่าจะเปลี่ยนค่า นี่คือสาเหตุที่พบบ่อยที่สุดที่ทำให้ผลค้นหาว่าง และปุ่ม ' + B('clear') + ' <b>ไม่ได้</b>รีเซ็ตวันที่')}</p>")}

<h3>{t("Product name and Ass. job no.", "ชื่อผลิตภัณฑ์และเลขที่ใบสั่งงาน")}</h3>
<ul>
<li>{t("Type a value or pick one from the drop-down. A value you type that is not in the list is still used.", "พิมพ์ค่าหรือเลือกจากรายการ หากพิมพ์ค่าที่ไม่อยู่ในรายการ ระบบก็ยังใช้ค่านั้นกรอง")}</li>
<li>{t("The lists are <b>cascading</b>: they only offer values that exist for the chosen date, and the product list narrows further once an Ass. job no. is chosen. Each list shows up to 300 values.", "รายการเป็นแบบ<b>เชื่อมโยงกัน</b>: แสดงเฉพาะค่าที่มีอยู่ในวันที่ที่เลือก และรายการชื่อผลิตภัณฑ์จะแคบลงอีกเมื่อเลือกเลขที่ใบสั่งงาน แต่ละรายการแสดงได้สูงสุด 300 ค่า")}</li>
<li>{t("The match is exact (equal to what you typed).", "ใช้การจับคู่แบบตรงทุกตัวอักษร (เท่ากับที่พิมพ์)")}</li>
</ul>

<h3>{t("Category, Tag and Value — find one specific serial", "ระดับบรรจุภัณฑ์ พารามิเตอร์ และค่า — ค้นหารหัสที่ต้องการ")}</h3>
{steps([
    t(f"Pick a {U('category')}: {lvl('unit')}, {lvl('inner')}, {lvl('display')} or {lvl('carton')}.", f"เลือก{U('category')}: {lvl('unit')} {lvl('inner')} {lvl('display')} หรือ {lvl('carton')}"),
    t(f"Pick a {U('tag')}: {lvl('serial_no')}, {lvl('roll_no')}, {lvl('source_id')} or {lvl('target_id')} (only those that exist for that level are offered). {U('serial_no')} is chosen for you.", f"เลือก{U('tag')}: {lvl('serial_no')} {lvl('roll_no')} {lvl('source_id')} หรือ {lvl('target_id')} (แสดงเฉพาะที่มีในระดับนั้น) ระบบเลือก {U('serial_no')} ให้อัตโนมัติ"),
    t(f"Type or scan the {U('value')}, or pick one from the list (typing narrows the list).", f"พิมพ์หรือสแกน{U('value')} หรือเลือกจากรายการ (พิมพ์เพื่อกรองรายการ)"),
    t(f"Press <kbd>Enter</kbd> in the Value box, or click {B('search', 'blue')}.", f"กด <kbd>Enter</kbd> ในช่องค่า หรือคลิก {B('search', 'blue')}"),
])}
{callout("note", t("Exact match", "จับคู่แบบตรงทุกตัวอักษร"), f"<p>{t('The value must match <b>exactly</b>, ignoring upper/lower case: searching for <code>1</code> finds <code>1</code> but not <code>10</code> or <code>201</code>. You may use <code>%</code> (any characters) and <code>_</code> (one character) as wildcards.', 'ค่าต้องตรงกัน<b>ทุกตัวอักษร</b> โดยไม่สนใจตัวพิมพ์เล็ก/ใหญ่ เช่น ค้นหา <code>1</code> จะพบ <code>1</code> แต่ไม่พบ <code>10</code> หรือ <code>201</code> สามารถใช้ <code>%</code> (กี่ตัวอักษรก็ได้) และ <code>_</code> (หนึ่งตัวอักษร) เป็นตัวแทนได้')}</p>")}
<p>{t("If the filter is incomplete the search still runs, and the status line warns you, for example", "หากกรอกตัวกรองไม่ครบ ระบบยังค้นหาให้ และบรรทัดสถานะจะแจ้งเตือน เช่น")} {M(t("category/tag filter skipped (no value entered)", "ข้ามตัวกรองระดับบรรจุภัณฑ์/พารามิเตอร์ (ยังไม่ได้กรอกค่า)"))}.</p>

<h3>{t("Search, Clear and folding the panel", "ค้นหา ล้าง และการพับแผงตัวกรอง")}</h3>
{table([t("Control", "ปุ่ม"), t("Effect", "ผล")], [
    [B("search", "blue"), t("Loads the Records grid using the filters. It also leaves any single-container view (see “Showing the records in …”).", "โหลดตารางข้อมูลตามตัวกรอง และออกจากมุมมองเฉพาะบรรจุภัณฑ์ (ดู “กำลังแสดงข้อมูลใน …”)")],
    [B("clear", "blue"), t("Empties Ass. job no., Product name, Category, Tag and Value and returns the Container manager to “All cartons”. It does <b>not</b> reset the date and does <b>not</b> reload or empty the grid — rows already shown stay until you search again.", "ล้างเลขที่ใบสั่งงาน ชื่อผลิตภัณฑ์ ระดับบรรจุภัณฑ์ พารามิเตอร์ และค่า และพาตัวจัดการบรรจุภัณฑ์กลับไปที่ “ลังทั้งหมด” แต่<b>ไม่</b>รีเซ็ตวันที่ และ<b>ไม่</b>โหลดหรือเคลียร์ตารางใหม่ แถวที่แสดงอยู่จะยังอยู่จนกว่าจะค้นหาอีกครั้ง")],
    [f"{B('hide_filters', 'light')} / {B('show_filters', 'light')}", t("Folds the panel to one line that still summarises what is filtered (for example “Filtering by October 2026 · AJ-26-0042”). The Records tab starts unfolded; the Container manager tab starts folded. Each tab remembers your choice.", "พับแผงเหลือบรรทัดเดียวที่ยังสรุปตัวกรองไว้ (เช่น “กรองด้วย ตุลาคม 2026 · AJ-26-0042”) แท็บรายการข้อมูลเริ่มต้นแบบกางออก แท็บจัดการบรรจุภัณฑ์เริ่มต้นแบบพับ และแต่ละแท็บจำค่าที่คุณเลือก")],
])}
{figure("filters_folded_%s.png" % lang, t("The filter panel folded away: the summary line still tells you what is filtered.", "แผงตัวกรองที่พับอยู่: บรรทัดสรุปยังบอกว่ากรองด้วยอะไร"))}
""")

    # ------------------------------------------------------------------ 6
    chapter("records", "The Records tab", "แท็บรายการข้อมูล", f"""
<h3>{t("Loading records", "การโหลดข้อมูล")}</h3>
<p>{t(f"Set your filters and click {B('search', 'blue')}. The status line reports ", f"ตั้งตัวกรองแล้วคลิก {B('search', 'blue')} บรรทัดสถานะจะแสดง ")}{M(t("24 row(s) loaded.", "โหลดแล้ว 24 แถว"))}</p>
{callout("warn", t("The grid shows at most 500 rows", "ตารางแสดงได้สูงสุด 500 แถว"), f"<p>{t('Rows come back in no particular order and the list stops at 500. If you see exactly 500, there are probably more: narrow the filters (day, job, a specific serial). Sorting a column only re-orders the rows already loaded; it does not fetch the “first” or “last” ones.', 'ข้อมูลจะไม่เรียงลำดับตายตัวและหยุดที่ 500 แถว หากเห็น 500 แถวพอดี แสดงว่ามีมากกว่านั้น ให้กรองให้แคบลง (วัน ใบสั่งงาน หรือรหัสเฉพาะ) การจัดเรียงคอลัมน์เป็นเพียงการเรียงแถวที่โหลดแล้ว ไม่ได้ดึงแถวแรกหรือแถวสุดท้ายจริง ๆ')}</p>")}

<h3>{t("Reading the grid", "การอ่านตาราง")}</h3>
<ul>
<li>{t("Each row is one unit. The columns begin with the record <code>id</code>, the job, product and creation time, followed by four columns for each level: Serial No, Roll No, Source ID and Target ID.", "แต่ละแถวคือหนึ่งหน่วยสินค้า คอลัมน์เริ่มจากรหัสข้อมูล <code>id</code> เลขที่ใบสั่งงาน ชื่อผลิตภัณฑ์ และเวลาที่สร้าง ตามด้วยสี่คอลัมน์ของแต่ละระดับ ได้แก่ รหัสซีเรียล หมายเลขม้วน รหัสต้นทาง และรหัสปลายทาง")}</li>
<li>{t(f"<b>Hide columns</b> you do not need by unticking them in the {U('columns')} strip (scroll it sideways if it is long). Hiding only changes what you see.", f"<b>ซ่อนคอลัมน์</b>ที่ไม่ต้องการโดยเอาเครื่องหมายถูกออกในแถบ {U('columns')} (เลื่อนไปด้านข้างหากยาว) การซ่อนมีผลเฉพาะการแสดงผล")}</li>
<li>{t("<b>Sort</b> by clicking a column header: ▲ ascending, click again ▼ descending. Numbers sort as numbers. The delete-tick column cannot be sorted.", "<b>จัดเรียง</b>โดยคลิกหัวคอลัมน์: ▲ น้อยไปมาก คลิกอีกครั้ง ▼ มากไปน้อย ตัวเลขเรียงตามค่าตัวเลข คอลัมน์ช่องติ๊กลบจัดเรียงไม่ได้")}</li>
<li>{t("Drag the edge of a header to change a column’s width. Click, drag, or Shift/Ctrl-click to select rows.", "ลากขอบหัวคอลัมน์เพื่อปรับความกว้าง คลิก ลาก หรือใช้ Shift/Ctrl+คลิกเพื่อเลือกหลายแถว")}</li>
</ul>

<h3>{t("Editing cells (admins)", "การแก้ไขเซลล์ (ผู้ดูแลระบบ)")}</h3>
{steps([
    t("Double-click a cell (or select it and press <kbd>F2</kbd>), type the new value, press <kbd>Enter</kbd>.", "ดับเบิลคลิกเซลล์ (หรือเลือกแล้วกด <kbd>F2</kbd>) พิมพ์ค่าใหม่ แล้วกด <kbd>Enter</kbd>"),
    t("The cell turns <b style='background:#7fe0b0;color:#06301c;padding:0 5px;border-radius:3px'>green</b>: it is changed on screen but <b>not yet saved</b>. Typing the original value back removes the green.", "เซลล์จะเปลี่ยนเป็น<b style='background:#7fe0b0;color:#06301c;padding:0 5px;border-radius:3px'>สีเขียว</b> หมายถึงเปลี่ยนบนหน้าจอแล้วแต่<b>ยังไม่ได้บันทึก</b> พิมพ์ค่าเดิมกลับเข้าไปเพื่อเอาสีเขียวออก"),
    t(f"Edit as many cells as you need, then click {B('save', 'green')} (see below).", f"แก้ไขได้หลายเซลล์ แล้วคลิก {B('save', 'green')} (ดูด้านล่าง)"),
])}
{figure("records_edit_%s.png" % lang, t("A green cell (edited, unsaved) and a red row (marked for deletion).", "เซลล์สีเขียว (แก้ไขแล้ว ยังไม่บันทึก) และแถวสีแดง (ทำเครื่องหมายลบ)"))}
<h4>{t("Cells you cannot edit", "เซลล์ที่แก้ไขไม่ได้")}</h4>
<p>{t("The display, inner and carton <b>Serial No</b> and <b>Roll No</b> cells are read-only: one container label is shared by many rows, so changing it in one row would silently change it for the others. Hover over such a cell to read the explanation. To change a container serial, <b>right-click</b> the cell and choose <i>Rename this …</i> (see “Renaming a container”). Unit cells are editable because a unit belongs to exactly one row.", "เซลล์ <b>รหัสซีเรียล</b> และ <b>หมายเลขม้วน</b> ของกล่องแสดงสินค้า กล่องชั้นใน และลัง เป็นแบบอ่านอย่างเดียว เพราะรหัสบรรจุภัณฑ์หนึ่งใช้ร่วมกันหลายแถว การแก้ในแถวเดียวจะกระทบแถวอื่นโดยไม่รู้ตัว ชี้เมาส์ที่เซลล์เพื่ออ่านคำอธิบาย หากต้องการเปลี่ยนรหัสบรรจุภัณฑ์ ให้<b>คลิกขวา</b>ที่เซลล์แล้วเลือก <i>เปลี่ยนรหัส … นี้</i> (ดูหัวข้อ “การเปลี่ยนรหัสบรรจุภัณฑ์”) เซลล์ของหน่วยสินค้าแก้ไขได้ เพราะหน่วยสินค้าหนึ่งอยู่ในแถวเดียวเท่านั้น")}</p>
{callout("note", t("What changing a unit serial also does", "การเปลี่ยนรหัสซีเรียลของหน่วยสินค้ายังทำอะไรเพิ่มอีก"), "<ul>" + "".join(f"<li>{x}</li>" for x in [
    t("The <b>roll number</b> that belongs to the new serial is looked up in the serial inventory and filled in for you (unless you typed a roll number yourself in the same save).", "ระบบค้น<b>หมายเลขม้วน</b>ของรหัสใหม่จากคลังรหัสและกรอกให้ (เว้นแต่คุณพิมพ์หมายเลขม้วนเองในการบันทึกครั้งเดียวกัน)"),
    t("The <b>old serial is freed</b> (no longer in use) and the <b>new serial is marked in use</b>.", "<b>รหัสเดิมจะถูกปล่อยว่าง</b> (ไม่ได้ใช้งาน) และ<b>รหัสใหม่จะถูกทำเครื่องหมายว่าใช้งานอยู่</b>"),
    t("The new serial <b>must exist in the serial inventory</b>. If it does not, the save is refused and nothing is changed.", "รหัสใหม่<b>ต้องมีอยู่ในคลังรหัส</b> หากไม่มี ระบบจะปฏิเสธการบันทึกและไม่เปลี่ยนแปลงสิ่งใด"),
]) + "</ul>")}

<h3>{t("Deleting records (admins)", "การลบข้อมูล (ผู้ดูแลระบบ)")}</h3>
{steps([
    t(f"Tick the {U('del')} box at the start of each row you want to remove — or select rows (click, drag, Shift/Ctrl) and click {B('delete', 'light')} in the footer, which ticks them all.", f"ติ๊กช่อง {U('del')} ที่ต้นแถวที่ต้องการลบ — หรือเลือกแถว (คลิก ลาก Shift/Ctrl) แล้วคลิก {B('delete', 'light')} ที่ท้ายหน้าต่าง ระบบจะติ๊กให้ทั้งหมด"),
    t("The rows turn <b style='background:#f28b8b;color:#3d0606;padding:0 5px;border-radius:3px'>red</b>. Nothing is deleted yet. Untick the box to undo.", "แถวจะเปลี่ยนเป็น<b style='background:#f28b8b;color:#3d0606;padding:0 5px;border-radius:3px'>สีแดง</b> ยังไม่มีการลบจริง เอาเครื่องหมายถูกออกเพื่อย้อนกลับ"),
    t(f"Click {B('save', 'green')} and confirm.", f"คลิก {B('save', 'green')} แล้วยืนยัน"),
])}
<p>{t("When rows are deleted their unit serials are <b>freed</b>, their links are removed, and any display or inner box that is left with nothing inside is removed too (its serial is freed as well). Other rows in the same box are never touched. To remove a whole box and everything in it, use <b>Delete container</b> instead.",
      "เมื่อลบแถว รหัสซีเรียลของหน่วยสินค้าจะ<b>ถูกปล่อยว่าง</b> การเชื่อมโยงถูกลบ และกล่องแสดงสินค้าหรือกล่องชั้นในที่ไม่เหลือสิ่งใดอยู่ภายในจะถูกลบด้วย (รหัสของกล่องก็ถูกปล่อยว่างเช่นกัน) แถวอื่นในกล่องเดียวกันจะไม่ถูกแตะต้อง หากต้องการลบทั้งกล่องพร้อมทุกอย่างภายใน ให้ใช้ <b>ลบบรรจุภัณฑ์</b>")}</p>

<h3>{t("Saving", "การบันทึก")}</h3>
{steps([
    t(f"Click {B('save', 'green')}. If there is nothing to save the status line says ", f"คลิก {B('save', 'green')} หากไม่มีอะไรให้บันทึก บรรทัดสถานะจะแจ้ง ") + M(t("No changes to save.", "ไม่มีการเปลี่ยนแปลงที่จะบันทึก")),
    t("A confirmation asks, for example: <i>“This will update 1 row(s) and delete 1 row(s) in public.filling_product_logs. This cannot be undone. Continue?”</i> The default answer is <b>No</b>.", "หน้าต่างยืนยันจะถาม เช่น <i>“การดำเนินการนี้จะอัปเดต 1 แถว และลบ 1 แถว ใน public.filling_product_logs และไม่สามารถย้อนกลับได้ ต้องการดำเนินการต่อหรือไม่?”</i> ค่าเริ่มต้นคือ <b>ไม่</b>"),
    t("Click <b>Yes</b>. The status line reports " , "คลิก <b>ใช่</b> บรรทัดสถานะจะแจ้ง ") + M(t("Changes saved.", "บันทึกการเปลี่ยนแปลงแล้ว")) + t(" and the grid reloads with your changes.", " และตารางจะโหลดใหม่พร้อมการเปลี่ยนแปลงของคุณ"),
])}
<p>{t("Saving is <b>all or nothing</b>: every edit and deletion is written in one step, and if any part fails (for example a serial that is already in use) nothing is written at all. The error appears in red in the status line.", "การบันทึกเป็นแบบ<b>ทั้งหมดหรือไม่เลย</b>: ทุกการแก้ไขและการลบถูกเขียนในขั้นตอนเดียว หากส่วนใดล้มเหลว (เช่น รหัสที่ถูกใช้งานแล้ว) จะไม่มีอะไรถูกเขียนเลย ข้อผิดพลาดจะแสดงเป็นสีแดงในบรรทัดสถานะ")}</p>

<h3>{t("Cancel does not mean “undo”", "ยกเลิกไม่ได้หมายถึง “ย้อนกลับ”")}</h3>
{callout("stop", t("Cancel throws everything away", "ปุ่มยกเลิกทิ้งทุกอย่าง"), f"<p>{t('The footer ' + B('cancel', 'red') + ' button clears all the filters <b>and empties the grid</b>, discarding every unsaved edit and deletion mark — without asking. The status line says “Cleared.”. To undo a single edit, retype the original value; to undo a deletion mark, untick the box. To simply reload, use ' + B('search', 'blue') + '.', 'ปุ่ม ' + B('cancel', 'red') + ' ที่ท้ายหน้าต่างจะล้างตัวกรองทั้งหมด<b>และเคลียร์ตาราง</b> ทิ้งการแก้ไขและเครื่องหมายลบที่ยังไม่บันทึกทั้งหมดโดยไม่ถามยืนยัน บรรทัดสถานะจะแจ้ง “ล้างข้อมูลแล้ว” หากต้องการย้อนเพียงหนึ่งการแก้ไข ให้พิมพ์ค่าเดิมกลับ หากต้องการยกเลิกเครื่องหมายลบ ให้เอาเครื่องหมายถูกออก หรือหากต้องการโหลดใหม่ให้ใช้ ' + B('search', 'blue'))}</p>")}

<h3>{t("Right-click menu", "เมนูคลิกขวา")}</h3>
<p>{t("Right-click a display, inner or carton <b>Serial No</b> cell (admins) to get <i>Rename this display…</i> / <i>Delete this display…</i> (the word follows the column). The dialog opens with that serial already filled in.", "คลิกขวาที่เซลล์ <b>รหัสซีเรียล</b> ของกล่องแสดงสินค้า กล่องชั้นใน หรือลัง (ผู้ดูแลระบบ) จะได้เมนู <i>เปลี่ยนรหัสกล่องแสดงสินค้านี้…</i> / <i>ลบกล่องแสดงสินค้านี้…</i> (คำเปลี่ยนตามคอลัมน์) หน้าต่างจะเปิดพร้อมรหัสนั้นที่กรอกไว้ให้แล้ว")}</p>
<p>{t("Rename, Delete container, and opening a container’s records are <b>refused while you have unsaved edits</b>, because they reload the grid. Save or cancel first.", "การเปลี่ยนรหัส การลบบรรจุภัณฑ์ และการเปิดข้อมูลของบรรจุภัณฑ์ จะ<b>ถูกปฏิเสธเมื่อมีการแก้ไขที่ยังไม่บันทึก</b> เพราะต้องโหลดตารางใหม่ ให้บันทึกหรือยกเลิกก่อน")}</p>

<h3>{t("Showing one container’s records", "การแสดงข้อมูลเฉพาะบรรจุภัณฑ์")}</h3>
<p>{t(f"When you click {B('view_records')} on a container card, the grid shows only that container’s rows and a bar appears above it, such as “Showing the records in  ▢ C260800001 › ▢ I26080011 › ▢ D260800111”. Click {B('show_all_records', 'light')} to return to whatever the filter panel says. Your filters are never changed by this.", f"เมื่อคลิก {B('view_records')} ที่การ์ดบรรจุภัณฑ์ ตารางจะแสดงเฉพาะแถวของบรรจุภัณฑ์นั้น และมีแถบปรากฏด้านบน เช่น “กำลังแสดงข้อมูลใน ▢ C260800001 › ▢ I26080011 › ▢ D260800111” คลิก {B('show_all_records', 'light')} เพื่อกลับไปตามที่แผงตัวกรองกำหนด ตัวกรองของคุณจะไม่ถูกเปลี่ยนจากการนี้")}</p>
{figure("records_scope_%s.png" % lang, t("The grid scoped to one display, with the way back in the bar above it.", "ตารางที่แสดงเฉพาะกล่องแสดงสินค้าหนึ่งกล่อง พร้อมปุ่มกลับในแถบด้านบน"))}
""")

    # ------------------------------------------------------------------ 7
    chapter("containers", "The Container manager tab", "แท็บจัดการบรรจุภัณฑ์", f"""
<p>{t("This tab lets you browse the packing structure like folders: cartons contain inner boxes, inner boxes contain displays, displays contain units. Counts follow the active filters and include <b>all</b> matching saved rows (not limited to 500).",
      "แท็บนี้ให้คุณเรียกดูโครงสร้างการบรรจุเหมือนโฟลเดอร์: ลังบรรจุกล่องชั้นใน กล่องชั้นในบรรจุกล่องแสดงสินค้า และกล่องแสดงสินค้าบรรจุหน่วยสินค้า ตัวเลขเป็นไปตามตัวกรองที่ใช้ และนับ<b>ทุก</b>แถวที่ตรงเงื่อนไข (ไม่จำกัดที่ 500)")}</p>
{figure("containers_%s.png" % lang, t("Top level: one card per carton.", "ระดับบนสุด: การ์ดหนึ่งใบต่อหนึ่งลัง"))}

<h3>{t("Cards", "การ์ด")}</h3>
<p>{t("Each card is one container. The coloured top edge and icon show its level: <b style='color:#d98a0b'>carton</b> amber, <b style='color:#7a52c9'>inner</b> violet, <b style='color:#2c6aa0'>display</b> blue, <b style='color:#2f9e66'>unit</b> green. A card shows the serial, how many items are inside, and how many saved rows it covers.", "การ์ดแต่ละใบคือบรรจุภัณฑ์หนึ่งรายการ ขอบบนและไอคอนสีบอกระดับ: <b style='color:#d98a0b'>ลัง</b> สีเหลืองอำพัน <b style='color:#7a52c9'>กล่องชั้นใน</b> สีม่วง <b style='color:#2c6aa0'>กล่องแสดงสินค้า</b> สีน้ำเงิน <b style='color:#2f9e66'>หน่วยสินค้า</b> สีเขียว การ์ดแสดงรหัส จำนวนรายการภายใน และจำนวนแถวข้อมูลที่บันทึก")}</p>
{table([t("Button", "ปุ่ม"), t("What it does", "ผล")], [
    [B("open_box"), t("Goes <i>inside</i> this container and shows its children as cards.", "เข้าไป<i>ภายใน</i>บรรจุภัณฑ์นี้และแสดงรายการภายในเป็นการ์ด")],
    [B("view_records"), t("Switches to the Records tab showing only this container’s rows. (On a unit card this is the main button.)", "สลับไปแท็บรายการข้อมูลและแสดงเฉพาะแถวของบรรจุภัณฑ์นี้ (ในการ์ดหน่วยสินค้านี่คือปุ่มหลัก)")],
    [f'<span style="color:#2c6aa0">{lvl("rename")}</span>', t("Opens the Rename dialog for this serial (admins).", "เปิดหน้าต่างเปลี่ยนรหัสของรหัสนี้ (ผู้ดูแลระบบ)")],
    [f'<span style="color:#2c6aa0">{lvl("delete")}</span>', t("Opens the Delete container dialog for this serial (admins). Unit cards have no Delete — units are deleted in the Records grid.", "เปิดหน้าต่างลบบรรจุภัณฑ์ของรหัสนี้ (ผู้ดูแลระบบ) การ์ดหน่วยสินค้าไม่มีปุ่มลบ — ลบหน่วยสินค้าได้ที่ตารางรายการข้อมูล")],
])}
<p>{t(f"A card named {U('unassigned')} groups rows that have no container at that level. It has no serial, so it cannot be renamed or deleted.", f"การ์ดชื่อ {U('unassigned')} รวมแถวที่ไม่มีบรรจุภัณฑ์ในระดับนั้น ไม่มีรหัสจึงเปลี่ยนรหัสหรือลบไม่ได้")}</p>
<p>{t("If a product picture has been set up, cards can show it as a small thumbnail (unit cards by default; box cards when an image is configured for that level); click it to enlarge. (Pictures are added by IT — see <code>docs/product-avatars.md</code>.)", "หากมีการตั้งรูปผลิตภัณฑ์ไว้ การ์ดสามารถแสดงรูปย่อได้ (การ์ดหน่วยสินค้าเป็นค่าเริ่มต้น ส่วนการ์ดกล่องจะแสดงเมื่อมีการตั้งรูปสำหรับระดับนั้น) คลิกเพื่อขยาย (ฝ่าย IT เป็นผู้เพิ่มรูป — ดู <code>docs/product-avatars.md</code>)")}</p>

<h3>{t("Moving around", "การเลื่อนดู")}</h3>
{figure("containers_units_%s.png" % lang, t("Four levels deep: the trail “All cartons › carton › inner › display” sits above the unit cards.", "ลึกลงมาสี่ระดับ: เส้นทาง “ลังทั้งหมด › ลัง › กล่องชั้นใน › กล่องแสดงสินค้า” อยู่เหนือการ์ดหน่วยสินค้า"))}
<ul>
<li>{t(f"The <b>trail</b> at the top (“{lvl('all_cartons')} › carton › inner …”) shows where you are. Click any part of it to jump back there.", f"<b>เส้นทาง</b>ด้านบน (“{lvl('all_cartons')} › ลัง › กล่องชั้นใน …”) บอกตำแหน่งปัจจุบัน คลิกส่วนใดก็ได้เพื่อกระโดดกลับไปที่นั่น")}</li>
<li>{t("<b>←</b> and <b>→</b> are Back and Forward through the places you visited (keyboard: <kbd>Alt</kbd>+<kbd>←</kbd> / <kbd>Alt</kbd>+<kbd>→</kbd>). Hover to see where they lead. The page you were on at each level is remembered.", "<b>←</b> และ <b>→</b> คือย้อนกลับและไปข้างหน้าตามที่ที่เคยเข้าไป (แป้นพิมพ์: <kbd>Alt</kbd>+<kbd>←</kbd> / <kbd>Alt</kbd>+<kbd>→</kbd>) ชี้เมาส์เพื่อดูว่าจะไปที่ไหน โปรแกรมจำหน้าที่คุณเปิดค้างไว้ในแต่ละระดับ")}</li>
<li>{t(f"The box <i>{lvl('find_level')}</i> filters the cards on the current level by part of a serial.", f"ช่อง <i>{lvl('find_level')}</i> กรองการ์ดในระดับปัจจุบันตามส่วนหนึ่งของรหัส")}</li>
<li>{t(f"At the bottom, {B('prev', 'light')} / {B('next', 'light')} turn pages (as many cards fit as your window allows, up to 20 per page).", f"ด้านล่าง {B('prev', 'light')} / {B('next', 'light')} ใช้เปลี่ยนหน้า (จำนวนการ์ดต่อหน้าขึ้นกับขนาดหน้าต่าง สูงสุด 20)")}</li>
<li>{t(f"{B('refresh')} reloads the cards — use it after someone else has changed data.", f"{B('refresh')} โหลดการ์ดใหม่ — ใช้หลังมีผู้อื่นแก้ไขข้อมูล")}</li>
<li>{t(f"A strip such as “Filtering by AJ-26-0042” with {B('show_all', 'light')} explains why some containers are missing; {U('show_all')} clears job, product, category, tag and value (the date stays).", f"แถบ เช่น “กรองด้วย AJ-26-0042” พร้อม {B('show_all', 'light')} อธิบายว่าเหตุใดบางบรรจุภัณฑ์ไม่แสดง {U('show_all')} จะล้างใบสั่งงาน ผลิตภัณฑ์ ระดับ พารามิเตอร์ และค่า (วันที่ยังอยู่)")}</li>
</ul>
""")

    # ------------------------------------------------------------------ 8
    chapter("rename", "Renaming a container", "การเปลี่ยนรหัสบรรจุภัณฑ์", f"""
<p>{t("Use this when a carton, inner or display label carries the wrong serial, or when you need to change a unit serial by scanning it. A rename is applied <b>immediately</b>; it does not wait for Save. Admins only.", "ใช้เมื่อฉลากของลัง กล่องชั้นใน หรือกล่องแสดงสินค้ามีรหัสผิด หรือเมื่อต้องการเปลี่ยนรหัสหน่วยสินค้าด้วยการสแกน การเปลี่ยนรหัสมีผล<b>ทันที</b>ไม่ต้องรอกดบันทึก เฉพาะผู้ดูแลระบบ")}</p>
<p>{t("Start it from the footer button", "เริ่มได้จากปุ่มท้ายหน้าต่าง")} {B("rename_c")}{t(", the", " ปุ่ม")} {U("rename")} {t("link on a card, or by right-clicking a serial cell in the grid.", "บนการ์ด หรือคลิกขวาที่เซลล์รหัสในตาราง")}</p>
{figure("rename_%s.png" % lang, t("Stage 1 — the Rename dialog.", "ขั้นที่ 1 — หน้าต่างเปลี่ยนรหัส"), narrow=True)}
<h3>{t("Stage 1: rename the container", "ขั้นที่ 1: เปลี่ยนรหัสบรรจุภัณฑ์")}</h3>
{steps([
    t(f"Choose the {U('level')}: {lvl('carton')}, {lvl('inner')}, {lvl('display')} or {lvl('unit')}.", f"เลือก{U('level')}: {lvl('carton')} {lvl('inner')} {lvl('display')} หรือ {lvl('unit')}"),
    t("In the first box scan or type the <b>current</b> serial (or pick it from the list). Press <kbd>Enter</kbd> to jump to the second box. The line under the boxes tells you how much will change, e.g. <i>“12 row(s) and 15 link(s) name “I26080011”. All of them will be rewritten.”</i>", "ในช่องแรกให้สแกนหรือพิมพ์รหัส<b>ปัจจุบัน</b> (หรือเลือกจากรายการ) กด <kbd>Enter</kbd> เพื่อไปช่องที่สอง บรรทัดใต้ช่องจะบอกว่ามีอะไรเปลี่ยนบ้าง เช่น <i>“มี 12 แถวและ 15 การเชื่อมโยงที่อ้างถึง “I26080011” ทั้งหมดจะถูกอัปเดต”</i>"),
    t("In the second box scan or type the <b>new</b> serial. It starts filled with the old serial so you can edit just a few characters. A scanner’s <kbd>Enter</kbd> never submits the dialog.", "ในช่องที่สองให้สแกนหรือพิมพ์รหัส<b>ใหม่</b> ช่องนี้เริ่มต้นด้วยรหัสเดิมเพื่อให้แก้เพียงไม่กี่ตัวอักษร <kbd>Enter</kbd> จากเครื่องสแกนจะไม่ส่งหน้าต่าง"),
    t(f"Click {B('rename', 'blue')} (enabled once the new serial differs from the old).", f"คลิก {B('rename', 'blue')} (ใช้ได้เมื่อรหัสใหม่ต่างจากรหัสเดิม)"),
    t("Read the confirmation (it states the number of rows and links) and click <b>Yes</b>.", "อ่านหน้าต่างยืนยัน (ระบุจำนวนแถวและการเชื่อมโยง) แล้วคลิก <b>ใช่</b>"),
])}
<p>{t("The status line then reads, for example", "บรรทัดสถานะจะแจ้ง เช่น")} {M(t('Renamed inner "I26080011" to "I26089011" — 12 row(s), 15 link(s).', 'เปลี่ยนรหัสกล่องชั้นในจาก "I26080011" เป็น "I26089011" แล้ว — 12 แถว, 15 การเชื่อมโยง'))}</p>
<p>{t("The rename rewrites every row and link that names the serial, carries the roll number along, <b>frees the old serial and marks the new one in use</b>. It is refused (and nothing changes) if the new serial is already used somewhere, if the old one does not exist, or if the new serial is not in the serial inventory.", "การเปลี่ยนรหัสจะอัปเดตทุกแถวและการเชื่อมโยงที่อ้างถึงรหัสนั้น เปลี่ยนหมายเลขม้วนตาม <b>ปล่อยรหัสเดิมให้ว่างและทำเครื่องหมายรหัสใหม่ว่าใช้งานอยู่</b> ระบบจะปฏิเสธ (และไม่เปลี่ยนอะไร) หากรหัสใหม่ถูกใช้ที่อื่นแล้ว รหัสเดิมไม่มีอยู่ หรือรหัสใหม่ไม่อยู่ในคลังรหัส")}</p>

<h3>{t("Stage 2: rename the children (after a carton, inner or display)", "ขั้นที่ 2: เปลี่ยนรหัสรายการภายใน (หลังเปลี่ยนรหัสลัง กล่องชั้นใน หรือกล่องแสดงสินค้า)")}</h3>
<p>{t("If the renamed carton, inner or display holds anything (inner boxes, displays or units), a second window, <b>Rename children</b>, lists what it holds. It is a separate step <i>after</i> the parent rename has already been saved.", "หากลัง กล่องชั้นใน หรือกล่องแสดงสินค้าที่เปลี่ยนรหัสมีสิ่งอื่นอยู่ภายใน (กล่องชั้นใน กล่องแสดงสินค้า หรือหน่วยสินค้า) จะมีหน้าต่างที่สอง <b>เปลี่ยนรหัสรายการภายใน</b> แสดงรายการเหล่านั้น เป็นขั้นตอนแยกที่เกิด<i>หลัง</i>บันทึกการเปลี่ยนรหัสของบรรจุภัณฑ์หลักไปแล้ว")}</p>
{figure("rename_children_%s.png" % lang, t("Stage 2 — carry the new naming down to the children you choose.", "ขั้นที่ 2 — เปลี่ยนรหัสตามลงไปยังรายการภายในที่เลือก"), narrow=True)}
{bullets([
    t("Each row shows the old serial, a suggested new serial and how many items are inside. The suggestion replaces the old parent code found inside the child’s serial with the new one; if the child’s serial does not contain it, the suggestion is unchanged and nothing will be renamed until you type a new value.", "แต่ละแถวแสดงรหัสเดิม รหัสใหม่ที่เสนอ และจำนวนรายการภายใน ข้อเสนอคือแทนที่รหัสของบรรจุภัณฑ์หลักเดิมที่อยู่ในรหัสของรายการภายในด้วยรหัสใหม่ หากรหัสนั้นไม่มีส่วนดังกล่าว ข้อเสนอจะเหมือนเดิมและจะไม่มีการเปลี่ยนจนกว่าจะพิมพ์ค่าใหม่"),
    t(f"Tick the rows to rename (use {U('select_all')} / {U('select_none')}), and edit any new serial by hand.", f"ติ๊กแถวที่ต้องการเปลี่ยนรหัส (ใช้ {U('select_all')} / {U('select_none')}) และแก้รหัสใหม่เองได้"),
    t(f"The button reads {B('apply')} or “Apply N change(s)”. It stays disabled while two children would get the same serial (a warning says which).", f"ปุ่มแสดง {B('apply')} หรือ “ใช้การเปลี่ยนแปลง N รายการ” จะใช้ไม่ได้ขณะที่รายการภายในสองรายการจะได้รหัสซ้ำกัน (มีคำเตือนบอกรหัสที่ซ้ำ)"),
    t(f"{B('skip')} closes the window and leaves the children as they are. <b>The parent rename stays in place either way.</b>", f"{B('skip')} ปิดหน้าต่างและคงรายการภายในไว้ตามเดิม <b>การเปลี่ยนรหัสของบรรจุภัณฑ์หลักยังคงอยู่ไม่ว่าเลือกแบบใด</b>"),
])}
{callout("warn", t("There is no Undo", "ไม่มีปุ่มย้อนกลับ"), f"<p>{t('To reverse a rename you must rename it back, which is a new rename subject to the same checks. Check the serials and counts in the confirmation before you click Yes.', 'หากต้องการย้อนการเปลี่ยนรหัส ต้องเปลี่ยนรหัสกลับ ซึ่งเป็นการเปลี่ยนรหัสใหม่และต้องผ่านการตรวจสอบเดียวกัน โปรดตรวจรหัสและจำนวนในหน้าต่างยืนยันก่อนคลิกใช่')}</p>")}
""")

    # ------------------------------------------------------------------ 9
    chapter("delete", "Deleting a container", "การลบบรรจุภัณฑ์", f"""
<p>{t("Deleting a container removes the box <b>and everything inside it</b>: its saved rows, its links and everything below it. Admins only; it happens <b>immediately</b>, not at Save. Start it from", "การลบบรรจุภัณฑ์จะลบกล่อง<b>พร้อมทุกอย่างที่อยู่ภายใน</b> ได้แก่ แถวข้อมูล การเชื่อมโยง และรายการทั้งหมดที่อยู่ลึกลงไป เฉพาะผู้ดูแลระบบ และมีผล<b>ทันที</b>ไม่ต้องรอกดบันทึก เริ่มได้จาก")} {B("delete_c")}, {t("the", "ลิงก์")} {U("delete")} {t("link on a card, or by right-clicking a serial cell.", "บนการ์ด หรือคลิกขวาที่เซลล์รหัส")}</p>
{figure("delete_%s.png" % lang, t("The Delete container dialog lists everything that will go before you confirm.", "หน้าต่างลบบรรจุภัณฑ์แสดงทุกอย่างที่จะถูกลบก่อนยืนยัน"), narrow=True)}
{steps([
    t(f"Choose the {U('level')}: {lvl('carton')}, {lvl('inner')} or {lvl('display')} (units are deleted in the Records grid).", f"เลือก{U('level')}: {lvl('carton')} {lvl('inner')} หรือ {lvl('display')} (ลบหน่วยสินค้าได้ที่ตารางรายการข้อมูล)"),
    t("Scan, type or pick the serial. <b>No container is pre-selected</b> and the Delete button stays disabled until a container has been found.", "สแกน พิมพ์ หรือเลือกรหัส <b>ระบบไม่เลือกบรรจุภัณฑ์ไว้ล่วงหน้า</b> และปุ่มลบจะใช้ไม่ได้จนกว่าจะพบบรรจุภัณฑ์"),
    t("Read the list under <b>Inside this container</b> (nested items are indented) and the summary, e.g. <i>“12 unit(s) · 12 saved row(s) · 15 link(s) will be deleted.”</i> If a parent box would be left empty by this, a line says it will be removed too.", "อ่านรายการใต้ <b>ภายในบรรจุภัณฑ์นี้</b> (รายการซ้อนจะเยื้องเข้าไป) และสรุป เช่น <i>“จะลบหน่วยสินค้า 12 รายการ · ข้อมูลที่บันทึก 12 แถว · 15 การเชื่อมโยง”</i> หากกล่องแม่จะว่างเปล่าเพราะการลบนี้ จะมีบรรทัดแจ้งว่าจะถูกลบด้วย"),
    t(f"Click {B('delete', 'red')}. <kbd>Enter</kbd> never confirms. A final question states the exact numbers; answer <b>Yes</b> to proceed.", f"คลิก {B('delete', 'red')} <kbd>Enter</kbd> ไม่เคยเป็นการยืนยัน คำถามสุดท้ายจะระบุจำนวนที่แน่นอน ตอบ <b>ใช่</b> เพื่อดำเนินการ"),
])}
<p>{t("On success", "เมื่อสำเร็จ")} {M(t('Deleted inner "I26080011" — 12 row(s), 15 link(s), 12 unit serial(s) released.', 'ลบกล่องชั้นใน "I26080011" แล้ว — 12 แถว, 15 การเชื่อมโยง, คืนรหัสซีเรียลของหน่วยสินค้า 12 รายการ'))} {t("The serials of the container and everything under it are freed so they can be used again.", "รหัสซีเรียลของบรรจุภัณฑ์และรายการทั้งหมดภายในจะถูกปล่อยว่างเพื่อใช้ใหม่ได้")}</p>
<h3>{t("Safeguards", "การป้องกันความผิดพลาด")}</h3>
{bullets([
    t("If the contents changed between the moment you looked and the moment you confirmed (someone else is working on it), the delete is refused and <b>nothing is deleted</b>.", "หากเนื้อหาเปลี่ยนไประหว่างที่คุณดูกับตอนยืนยัน (มีผู้อื่นกำลังแก้ไข) ระบบจะปฏิเสธการลบและ<b>ไม่ลบอะไรเลย</b>"),
    t("It refuses when the serial names more than one container, or when a container sits under more than one parent, rather than guessing.", "ระบบปฏิเสธเมื่อรหัสตรงกับบรรจุภัณฑ์มากกว่าหนึ่งรายการ หรือเมื่อบรรจุภัณฑ์อยู่ใต้กล่องแม่มากกว่าหนึ่งใบ แทนที่จะเดา"),
    t("Pending grid edits must be saved or cancelled first.", "ต้องบันทึกหรือยกเลิกการแก้ไขที่ค้างอยู่ในตารางก่อน"),
])}
{callout("stop", t("This cannot be undone", "ไม่สามารถย้อนกลับได้"), f"<p>{t('A deleted container, its rows and its links are gone. Always read the “Inside this container” list first.', 'บรรจุภัณฑ์ที่ลบ แถวข้อมูล และการเชื่อมโยงจะหายไปถาวร โปรดอ่านรายการ “ภายในบรรจุภัณฑ์นี้” ทุกครั้งก่อนลบ')}</p>")}
""")

    # ------------------------------------------------------------------ 10
    chapter("damage", "Report damage", "Report damage (แจ้งความเสียหาย)", f"""
<p>{t("Use this tab to flag a serial as <b>damaged</b> — for example a label that is destroyed and can never be scanned again. It works for a serial at any level: unit, display, inner or carton.", "ใช้แท็บนี้เพื่อทำเครื่องหมายรหัสซีเรียลว่า<b>เสียหาย</b> เช่น ฉลากที่ชำรุดและสแกนอีกไม่ได้ ใช้ได้กับรหัสทุกระดับ: หน่วยสินค้า กล่องแสดงสินค้า กล่องชั้นใน และลัง")}</p>
{figure("damage_%s.png" % lang, t("The Report damage tab.", "แท็บ Report damage"), narrow=False)}
{steps([
    t(f"Open the {TAB('damage')} tab. The cursor is already in the box.", f"เปิดแท็บ {TAB('damage')} เคอร์เซอร์จะอยู่ในช่องกรอกอยู่แล้ว"),
    t(f"Scan or type the damaged serial and press <kbd>Enter</kbd> (or click {B('damage', 'red')}).", f"สแกนหรือพิมพ์รหัสที่เสียหายแล้วกด <kbd>Enter</kbd> (หรือคลิก {B('damage', 'red')})"),
    t("On success the status below the box reads", "เมื่อสำเร็จ ข้อความใต้ช่องจะแจ้ง") + " " + M('Reported "U2608012345" damaged.') + t(" and the box is cleared, ready for the next scan.", " และช่องจะถูกล้างเพื่อพร้อมสแกนรหัสถัดไป"),
])}
<h3>{t("Only a serial that is not in use can be reported", "รายงานได้เฉพาะรหัสที่ไม่ได้ใช้งานอยู่")}</h3>
<p>{t("If the serial is still attached to a unit or container in production, a window <b>Serial in use</b> asks whether to open it in the records editor.", "หากรหัสนั้นยังผูกอยู่กับหน่วยสินค้าหรือบรรจุภัณฑ์ในสายการผลิต จะมีหน้าต่าง <b>Serial in use</b> ถามว่าต้องการเปิดในตารางข้อมูลหรือไม่")}</p>
{steps([
    t("Click <b>Yes</b>. DataRework switches to the Records tab, filtered to that serial.", "คลิก <b>ใช่</b> DataRework จะสลับไปแท็บรายการข้อมูลและกรองตามรหัสนั้น"),
    t("Take the serial out of use: delete the unit’s row, or delete the container, or rename the container onto a different serial (this frees the old one).", "ทำให้รหัสพ้นจากการใช้งาน: ลบแถวของหน่วยสินค้า หรือลบบรรจุภัณฑ์ หรือเปลี่ยนรหัสบรรจุภัณฑ์ไปเป็นรหัสอื่น (รหัสเดิมจะถูกปล่อยว่าง)"),
    t("Return to the Report damage tab and report the serial again.", "กลับมาที่แท็บ Report damage แล้วรายงานรหัสอีกครั้ง"),
])}
<ul>
<li>{t("If the serial is not in the serial inventory at all, you see", "หากรหัสไม่มีอยู่ในคลังรหัสเลย จะแสดง")} {M('No serial "X" found in staging_serial_data.')} {t("Check for a typing mistake.", "ให้ตรวจว่าพิมพ์ผิดหรือไม่")}</li>
<li>{t("The damaged total for the roll updates within about 10 seconds (background service).", "ยอดเสียหายของม้วนจะอัปเดตภายในประมาณ 10 วินาที (บริการเบื้องหลัง)")}</li>
</ul>
{callout("warn", t("Immediate, with no confirmation and no undo", "ทันที ไม่มีการยืนยัน และไม่มีปุ่มย้อนกลับ"), f"<p>{t('Pressing <kbd>Enter</kbd> reports the serial at once. The app does not record who reported it or when, and offers no way to clear the flag. Double-check what you scanned. This tab does not delete or alter any records; it only flags the serial in the inventory.', 'การกด <kbd>Enter</kbd> จะรายงานรหัสทันที โปรแกรมไม่บันทึกว่าใครรายงานและเมื่อใด และไม่มีวิธีล้างเครื่องหมายนี้ โปรดตรวจรหัสที่สแกนให้ดี แท็บนี้ไม่ลบหรือแก้ไขข้อมูลใด ๆ เพียงทำเครื่องหมายรหัสในคลังเท่านั้น')}</p>")}
""")

    # ------------------------------------------------------------------ 11
    chapter("status", "Status line and logs", "บรรทัดสถานะและบันทึก", f"""
<p>{t("The line at the bottom left is the status line. <b style='color:#1f7a4d'>Green</b> means the last action worked; <b style='color:#b23b35'>red</b> means it did not. It shows one short sentence. Search warnings (for example a filter that was skipped) are appended after the row count.", "บรรทัดที่มุมซ้ายล่างคือบรรทัดสถานะ <b style='color:#1f7a4d'>สีเขียว</b>หมายถึงการทำงานล่าสุดสำเร็จ <b style='color:#b23b35'>สีแดง</b>หมายถึงไม่สำเร็จ แสดงเป็นประโยคสั้น ๆ คำเตือนจากการค้นหา (เช่น ตัวกรองที่ถูกข้าม) จะต่อท้ายจำนวนแถว")}</p>
<h3>{t("The error log", "บันทึกข้อผิดพลาด")}</h3>
<p>{t(f"Click {B('log', 'light')} to open the <b>{lvl('error_log')}</b> window. It lists the most recent errors with the time and the message, newest last. Tick <b>Show technical details</b> to add the technical detail behind each error; <b>Copy</b> always includes it. It stays open while you keep working.", f"คลิก {B('log', 'light')} เพื่อเปิดหน้าต่าง<b>{lvl('error_log')}</b> แสดงข้อผิดพลาดล่าสุดพร้อมเวลาและข้อความ โดยรายการใหม่สุดอยู่ท้าย ติ๊ก<b>แสดงรายละเอียดทางเทคนิค</b>เพื่อดูรายละเอียดทางเทคนิคของแต่ละข้อผิดพลาด ส่วนปุ่ม<b>คัดลอก</b>จะคัดลอกรายละเอียดทั้งหมดเสมอ หน้าต่างนี้เปิดค้างไว้ได้ขณะทำงานต่อ")}</p>
{figure("log_%s.png" % lang, t("The error log window.", "หน้าต่างบันทึกข้อผิดพลาด"), narrow=True)}
{bullets([
    t(f"{B('copy', 'light')} copies the whole log to the clipboard — paste it into your message when you ask IT for help.", f"{B('copy', 'light')} คัดลอกบันทึกทั้งหมดไปยังคลิปบอร์ด — วางในข้อความเมื่อขอความช่วยเหลือจาก IT"),
    t(f"{B('clear', 'light')} empties the log; {B('close', 'light')} closes the window.", f"{B('clear', 'light')} ล้างบันทึก; {B('close', 'light')} ปิดหน้าต่าง"),
    t("The log holds the last 500 entries in memory only. It is <b>never saved to disk</b> and is lost when you close DataRework, so copy it before you quit.", "บันทึกเก็บ 500 รายการล่าสุดในหน่วยความจำเท่านั้น <b>ไม่เคยบันทึกลงดิสก์</b> และจะหายเมื่อปิด DataRework ดังนั้นให้คัดลอกก่อนปิดโปรแกรม"),
])}
<h3>{t("The activity log (audit trail)", "บันทึกกิจกรรม (audit log)")}</h3>
<p>{t("Separately from the error log, DataRework writes a permanent record of what was done, so it can later be checked who changed what and from which computer. You do not have to do anything — it is written automatically. It is a plain text file, not a window in the program.", "นอกจากบันทึกข้อผิดพลาดแล้ว DataRework ยังเขียนบันทึกถาวรว่ามีการทำอะไรไปบ้าง เพื่อให้ตรวจสอบย้อนหลังได้ว่าใครเปลี่ยนอะไรจากเครื่องไหน ไม่ต้องทำอะไรเพิ่ม ระบบเขียนให้อัตโนมัติ เป็นไฟล์ข้อความธรรมดา ไม่ใช่หน้าต่างในโปรแกรม")}</p>
{bullets([
    t("<b>Where:</b> the <code>logs</code> folder next to <code>DataRework.exe</code>. A new file is started every day, named <code>audit-YYYY-MM-DD.log</code> (for example <code>audit-2026-10-19.log</code>). Old days are kept; nothing is deleted automatically.", "<b>อยู่ที่ไหน:</b> โฟลเดอร์ <code>logs</code> ข้างไฟล์ <code>DataRework.exe</code> ระบบสร้างไฟล์ใหม่ทุกวัน ตั้งชื่อเป็น <code>audit-YYYY-MM-DD.log</code> (เช่น <code>audit-2026-10-19.log</code>) ไฟล์ของวันก่อน ๆ จะเก็บไว้ ไม่มีการลบอัตโนมัติ"),
    t("<b>What is recorded:</b> signing in, signing out (closing the main window), saving, changing a container, renaming, deleting and reporting damage. Only actions that <b>succeeded</b> are recorded; refused or failed ones appear in the error log instead.", "<b>บันทึกอะไรบ้าง:</b> การเข้าสู่ระบบ การออกจากระบบ (ปิดหน้าต่างหลัก) การบันทึก การเปลี่ยนบรรจุภัณฑ์ การเปลี่ยนรหัส การลบ และการแจ้งความเสียหาย บันทึกเฉพาะการกระทำที่ <b>สำเร็จ</b> ส่วนที่ถูกปฏิเสธหรือล้มเหลวจะอยู่ในบันทึกข้อผิดพลาดแทน"),
    t("<b>Save</b> writes a summary line (how many rows were updated, deleted or skipped because they were already transferred) and then one line per row. If a save edits a container serial (display, inner or carton), that row also gets a <b>Change container</b> line.", "<b>การบันทึก</b>จะเขียนบรรทัดสรุป (จำนวนแถวที่แก้ไข ลบ หรือข้ามเพราะถูกโอนแล้ว) แล้วตามด้วยหนึ่งบรรทัดต่อหนึ่งแถว หากการบันทึกแก้ไขรหัสบรรจุภัณฑ์ (display, inner หรือ carton) แถวนั้นจะมีบรรทัด <b>Change container</b> เพิ่มด้วย"),
])}
{table([t("Part of each line", "ส่วนของแต่ละบรรทัด"), t("Meaning", "ความหมาย")], [
    ["<code>time</code>", t("Date and time on this computer", "วันที่และเวลาของเครื่องนี้")],
    ["<code>VM_ID</code>", t("Which computer wrote the line (the <code>VM_ID</code> value in <code>.env</code>)", "เครื่องที่เขียนบรรทัดนี้ (ค่า <code>VM_ID</code> ใน <code>.env</code>)")],
    ["<code>tag_name</code>", t("The tag of the person signed in", "แท็กของผู้ที่เข้าสู่ระบบ")],
    ["<code>Activities</code>", t("What was done, with the serials involved", "สิ่งที่ทำ พร้อมรหัสซีเรียลที่เกี่ยวข้อง")],
])}
<p>{t("Example:", "ตัวอย่าง:")} <code>[time: 2026-10-19 13:00:48, VM_ID: 1, tag_name: ADMIN, Activities: Rename display "D26080011" -&gt; "D26089011" (12 row(s), 15 link(s))]</code></p>
{callout("note", t("Keep it private", "เก็บเป็นความลับ"), f"<p>{t('The activity log contains serial numbers and user tags. It is a record for supervisors and IT — do not edit it, and do not send it outside the company.', 'บันทึกกิจกรรมมีรหัสซีเรียลและแท็กผู้ใช้ เป็นบันทึกสำหรับหัวหน้างานและ IT — อย่าแก้ไข และอย่าส่งออกนอกบริษัท')}</p>")}
""")

    # ------------------------------------------------------------------ 12
    chapter("recipes", "Step-by-step recipes", "ขั้นตอนสำหรับงานที่ทำบ่อย", f"""
<h3>{t("A. Find one unit by scanning it", "ก. ค้นหาหน่วยสินค้าด้วยการสแกน")}</h3>
{steps([
    t(f"Set Month/Year to when it was made (or leave today’s), set {U('category')} = {lvl('unit')}, {U('tag')} = {lvl('serial_no')}.", f"ตั้งเดือน/ปีให้ตรงกับวันที่ผลิต (หรือใช้ของวันนี้) ตั้ง {U('category')} = {lvl('unit')} และ {U('tag')} = {lvl('serial_no')}"),
    t(f"Click into {U('value')}, scan the label. The scanner’s <kbd>Enter</kbd> runs the search.", f"คลิกที่ช่อง {U('value')} แล้วสแกนฉลาก <kbd>Enter</kbd> จากเครื่องสแกนจะค้นหาให้ทันที"),
    t("One row appears. Scroll right (or tick columns in the strip) to see its display, inner and carton.", "จะแสดงหนึ่งแถว เลื่อนไปทางขวา (หรือเลือกคอลัมน์ในแถบ) เพื่อดูกล่องแสดงสินค้า กล่องชั้นใน และลังของมัน"),
])}
<h3>{t("B. Correct a wrongly scanned unit serial", "ข. แก้รหัสหน่วยสินค้าที่สแกนผิด")}</h3>
{steps([
    t("Find the row (recipe A).", "ค้นหาแถว (สูตร ก)"),
    t("Double-click its Unit Serial No cell and type the correct serial. The cell turns green.", "ดับเบิลคลิกเซลล์รหัสซีเรียล (หน่วยสินค้า) แล้วพิมพ์รหัสที่ถูกต้อง เซลล์จะเป็นสีเขียว"),
    t(f"Click {B('save', 'green')} → <b>Yes</b>. If the correct serial is not in the inventory, the save is refused with a message that nothing was changed.", f"คลิก {B('save', 'green')} → <b>ใช่</b> หากรหัสที่ถูกต้องไม่มีในคลังรหัส ระบบจะปฏิเสธและแจ้งว่าไม่มีการเปลี่ยนแปลง"),
])}
<h3>{t("C. Take a unit out of its box", "ค. นำหน่วยสินค้าออกจากกล่อง")}</h3>
{steps([
    t("Find the row, tick its Del box, click Save → Yes.", "ค้นหาแถว ติ๊กช่อง ลบ ของแถวนั้น คลิกบันทึก → ใช่"),
    t("The unit’s serial is freed. If that was the last unit in a display, the empty display is removed too.", "รหัสของหน่วยสินค้าจะถูกปล่อยว่าง หากเป็นหน่วยสุดท้ายในกล่องแสดงสินค้า กล่องที่ว่างเปล่านั้นจะถูกลบด้วย"),
])}
<h3>{t("D. Fix a wrong carton, inner or display label", "ง. แก้ฉลากลัง กล่องชั้นใน หรือกล่องแสดงสินค้าที่ผิด")}</h3>
{steps([
    t(f"Click {B('rename_c')} (or right-click the serial in the grid).", f"คลิก {B('rename_c')} (หรือคลิกขวาที่รหัสในตาราง)"),
    t("Pick the level, scan the current serial, scan the new one, <b>Rename</b>, <b>Yes</b>.", "เลือกระดับ สแกนรหัสปัจจุบัน สแกนรหัสใหม่ <b>เปลี่ยนรหัส</b> <b>ใช่</b>"),
    t("In the Rename children window tick the children that should follow, <b>Apply</b> — or <b>Skip</b>.", "ในหน้าต่างเปลี่ยนรหัสรายการภายใน ติ๊กรายการที่ต้องเปลี่ยนตาม <b>นำไปใช้</b> — หรือ <b>ข้าม</b>"),
])}
<h3>{t("E. Remove an entire box", "จ. ลบกล่องทั้งใบ")}</h3>
{steps([
    t(f"Click {B('delete_c')}, pick the level, scan the serial.", f"คลิก {B('delete_c')} เลือกระดับ สแกนรหัส"),
    t("Read what is listed inside. Click Delete, then <b>Yes</b>.", "อ่านรายการภายใน คลิกลบ แล้วตอบ <b>ใช่</b>"),
])}
<h3>{t("F. Report a damaged label", "ฉ. แจ้งฉลากที่เสียหาย")}</h3>
{steps([
    t(f"Open {TAB('damage')}, scan the serial, <kbd>Enter</kbd>.", f"เปิดแท็บ {TAB('damage')} สแกนรหัส กด <kbd>Enter</kbd>"),
    t("If told it is still in use, answer Yes, free it (recipe C or E, or rename), then report again.", "หากแจ้งว่ายังใช้งานอยู่ ให้ตอบใช่ ปล่อยรหัสให้ว่าง (สูตร ค หรือ จ หรือเปลี่ยนรหัส) แล้วรายงานอีกครั้ง"),
])}
<h3>{t("G. See what is inside a carton", "ช. ดูว่าในลังมีอะไรบ้าง")}</h3>
{steps([
    t(f"Open {TAB('containers')}, find the carton card (use the search box if needed), click {B('open_box')}.", f"เปิดแท็บ {TAB('containers')} หาการ์ดลัง (ใช้ช่องค้นหาได้) แล้วคลิก {B('open_box')}"),
    t(f"Keep clicking {B('open_box')} to go down to displays and units, or {B('view_records')} to see the rows in the grid.", f"คลิก {B('open_box')} ต่อเพื่อลงไปถึงกล่องแสดงสินค้าและหน่วยสินค้า หรือ {B('view_records')} เพื่อดูแถวในตาราง"),
])}
""")

    # ------------------------------------------------------------------ 13
    chapter("trouble", "Troubleshooting", "การแก้ปัญหา", f"""
<p>{t("Messages appear in the status line (and in the error log).", "ข้อความจะแสดงในบรรทัดสถานะ (และในบันทึกข้อผิดพลาด) ข้อความของโปรแกรมแสดงเป็นภาษาไทยเมื่อเลือก TH แต่รายละเอียดข้อผิดพลาดจากฐานข้อมูล (เช่น Cannot save …, already in use …, matches 0 row(s) …) และข้อความของแท็บ Report damage จะยังเป็นภาษาอังกฤษ ในตารางนี้ข้อความที่ไม่ได้แปลจะแสดงเป็นอังกฤษตามที่เห็นบนหน้าจอ")}</p>
{table([t("Message", "ข้อความ"), t("Meaning", "ความหมาย"), t("What to do", "สิ่งที่ควรทำ")], [
    [M(t("Unable to reach the database", "ไม่สามารถเชื่อมต่อฐานข้อมูลได้")), t("The computer cannot reach the company database.", "เครื่องเชื่อมต่อฐานข้อมูลไม่ได้"), t("Check the network/VPN, retry. Nothing was changed. Contact IT if it continues.", "ตรวจเครือข่าย/VPN แล้วลองใหม่ ไม่มีการเปลี่ยนแปลงข้อมูล หากยังเป็นอยู่ให้ติดต่อ IT")],
    [M(t("Table \"public.…\" was not found.", "ไม่พบตาราง \"public.…\"")), t("The records table is missing or misconfigured.", "ไม่พบตารางข้อมูลหรือตั้งค่าผิด"), t("Tell IT; this is a configuration problem.", "แจ้ง IT เพราะเป็นปัญหาการตั้งค่า")],
    [M(t("Only admins can save changes.", "เฉพาะผู้ดูแลระบบเท่านั้นที่บันทึกการเปลี่ยนแปลงได้")), t("Your role is not admin / super admin.", "บทบาทของคุณไม่ใช่ผู้ดูแลระบบ"), t("Ask an administrator to make the change.", "ขอให้ผู้ดูแลระบบทำรายการแทน")],
    [M(t("Save or cancel your pending edits before …", "โปรดบันทึกหรือยกเลิกการแก้ไขที่ค้างอยู่ก่อน …")), t("You have green/red unsaved rows and tried to rename, delete a container or open container records.", "คุณมีแถวสีเขียว/แดงที่ยังไม่บันทึก แล้วพยายามเปลี่ยนรหัส ลบบรรจุภัณฑ์ หรือเปิดข้อมูลบรรจุภัณฑ์"), t("Click Save, or Cancel to discard, then retry.", "คลิกบันทึก หรือยกเลิกเพื่อทิ้งการแก้ไข แล้วลองใหม่")],
    [M("Cannot save: display_serial_no \"…\" is shared with N other row(s). …"), t("Your edit would change a container that other rows share.", "การแก้ไขของคุณจะเปลี่ยนบรรจุภัณฑ์ที่แถวอื่นใช้ร่วมกัน"), t("Nothing was saved. Use Rename container instead.", "ไม่มีการบันทึก ให้ใช้เปลี่ยนรหัสบรรจุภัณฑ์แทน")],
    [M("That serial already exists for this assignment/parent: …"), t("The new serial duplicates another one.", "รหัสใหม่ซ้ำกับรหัสอื่น"), t("Nothing was saved. Use a different serial.", "ไม่มีการบันทึก ใช้รหัสอื่น")],
    [M("Serial \"…\" matches 0 row(s) in staging_serial_data; expected exactly 1. Usage totals would be wrong, so nothing was changed."), t("The new serial is not registered in the serial inventory (0 rows), or is registered twice.", "รหัสใหม่ไม่ได้ลงทะเบียนในคลังรหัส (0 แถว) หรือลงทะเบียนซ้ำสองครั้ง"), t("Check the serial for typing mistakes. If it is correct, ask IT to add or fix its inventory entry.", "ตรวจการพิมพ์ หากถูกต้องให้ขอ IT เพิ่มหรือแก้รายการในคลังรหัส")],
    [M(t("Save failed: …", "บันทึกไม่สำเร็จ: …")), t("The database refused the save for another reason.", "ฐานข้อมูลปฏิเสธการบันทึกด้วยเหตุผลอื่น"), t("Nothing was saved. Open Log, Copy, and send it to IT.", "ไม่มีการบันทึก เปิดล็อก คัดลอก แล้วส่งให้ IT")],
    [M("Serial \"…\" is already in use — pick another."), t("Rename: the new serial is already on another row or link.", "การเปลี่ยนรหัส: รหัสใหม่ถูกใช้ในแถวหรือการเชื่อมโยงอื่นแล้ว"), t("Choose a serial that is not used.", "เลือกรหัสที่ยังไม่ถูกใช้")],
    [M("No carton named \"…\" exists in staging_product_logs."), t("Rename: the current serial does not exist at that level.", "การเปลี่ยนรหัส: ไม่มีรหัสปัจจุบันในระดับนั้น"), t("Check the level and the serial.", "ตรวจระดับและรหัส")],
    [M(t("Rename failed: …", "เปลี่ยนรหัสไม่สำเร็จ: …")), t("Another database problem during rename.", "ปัญหาฐานข้อมูลอื่นระหว่างเปลี่ยนรหัส"), t("Check Log; the parent rename is all-or-nothing.", "ดูล็อก การเปลี่ยนรหัสของบรรจุภัณฑ์หลักเป็นแบบทั้งหมดหรือไม่เลย")],
    [M(t("Children unchanged: …", "ไม่ได้เปลี่ยนรหัสรายการภายใน: …")), t("The parent was renamed, but renaming the children failed.", "เปลี่ยนรหัสบรรจุภัณฑ์หลักแล้ว แต่เปลี่ยนรหัสรายการภายในไม่สำเร็จ"), t("Rename the children again with Rename container.", "เปลี่ยนรหัสรายการภายในอีกครั้งด้วยปุ่มเปลี่ยนรหัสบรรจุภัณฑ์")],
    [M(t("Two children would share …", "รายการภายในสองรายการจะใช้รหัส … ซ้ำกัน")), t("Two rows in the Rename children window have the same new serial.", "สองแถวในหน้าต่างเปลี่ยนรหัสรายการภายในมีรหัสใหม่ซ้ำกัน"), t("Edit one of them.", "แก้ไขหนึ่งในสองรายการ")],
    [M("The contents of … changed since you looked … Nothing was deleted."), t("Someone changed the container while you had the Delete window open.", "มีผู้อื่นแก้ไขบรรจุภัณฑ์ขณะที่คุณเปิดหน้าต่างลบอยู่"), t("Open Delete container again and review the list.", "เปิดลบบรรจุภัณฑ์ใหม่และตรวจรายการอีกครั้ง")],
    [M("… is linked under more than one parent … refusing to guess"), t("The data shows the container under two parents.", "ข้อมูลแสดงว่าบรรจุภัณฑ์อยู่ใต้กล่องแม่สองใบ"), t("Do not force it; ask IT to correct the data.", "อย่าฝืนลบ ให้ขอ IT แก้ข้อมูล")],
    [M("The database refused to delete … Nothing was deleted."), t("A database rule blocked the delete and it was rolled back.", "กฎของฐานข้อมูลขัดขวางการลบและถูกยกเลิกทั้งหมด"), t("Copy the log and send it to IT.", "คัดลอกล็อกส่งให้ IT")],
    [M("… is still in use, so it cannot be reported damaged yet."), t("The serial is active in production.", "รหัสยังใช้งานอยู่ในสายการผลิต"), t("See “Report damage” — free it first.", "ดูหัวข้อ Report damage — ปล่อยให้ว่างก่อน")],
    [M("Could not find \"…\" in the records -- search for it manually."), t("The app could not tell which level the serial belongs to.", "โปรแกรมระบุไม่ได้ว่ารหัสอยู่ระดับใด"), t("Search for it yourself with Category/Tag/Value.", "ค้นหาเองด้วยระดับบรรจุภัณฑ์/พารามิเตอร์/ค่า")],
    [M(t("Unable to load containers. Try Refresh.", "ไม่สามารถโหลดบรรจุภัณฑ์ได้ โปรดลองรีเฟรช")), t("The Container manager could not load.", "โหลดจัดการบรรจุภัณฑ์ไม่สำเร็จ"), t("Click Refresh; check the connection.", "คลิกรีเฟรช ตรวจการเชื่อมต่อ")],
    [t("Search shows no rows", "ค้นหาแล้วไม่พบแถว"), t("Usually the date (Month/Year) or an old Value is still set.", "มักเกิดจากเดือน/ปีหรือค่าที่ค้างอยู่"), t("Check Month/Year first, then the other filters; click Clear and search again.", "ตรวจเดือน/ปีก่อน แล้วตรวจตัวกรองอื่น คลิกล้างและค้นหาใหม่")],
    [t("Serial totals do not change", "ยอดการใช้รหัสไม่เปลี่ยน"), t("The background service is not running, or it has not cycled yet (~10 s).", "บริการเบื้องหลังไม่ทำงาน หรือยังไม่ถึงรอบ (~10 วินาที)"), t("Wait 10–20 s; if still wrong, restart DataRework and accept the UAC prompt, or ask IT.", "รอ 10–20 วินาที หากยังผิด ให้เปิด DataRework ใหม่แล้วกดอนุญาต UAC หรือแจ้ง IT")],
])}
""")

    # ------------------------------------------------------------------ 14
    chapter("reference", "Quick reference", "สรุปอ้างอิงด่วน", f"""
<h3>{t("What each role can use", "บทบาทใดใช้อะไรได้")}</h3>
{table([t("Feature", "ฟังก์ชัน"), "admin / super admin", t("other roles", "บทบาทอื่น")], [
    [t("Search, filters, sort, hide columns", "ค้นหา ตัวกรอง จัดเรียง ซ่อนคอลัมน์"), ("✓", "yes"), ("✓", "yes")],
    [t("Browse Container manager, View records", "เรียกดูจัดการบรรจุภัณฑ์ ดูข้อมูล"), ("✓", "yes"), ("✓", "yes")],
    ["Report damage", ("✓", "yes"), ("✓", "yes")],
    [t("Error log", "บันทึกข้อผิดพลาด"), ("✓", "yes"), ("✓", "yes")],
    [t("Edit cells / mark rows for deletion / Save", "แก้ไขเซลล์ / ทำเครื่องหมายลบ / บันทึก"), ("✓", "yes"), ("✗", "no")],
    [t("Rename container", "เปลี่ยนรหัสบรรจุภัณฑ์"), ("✓", "yes"), ("✗", "no")],
    [t("Delete container", "ลบบรรจุภัณฑ์"), ("✓", "yes"), ("✗", "no")],
])}
<h3>{t("Limits to remember", "ข้อจำกัดที่ควรจำ")}</h3>
{table([t("Item", "รายการ"), t("Limit", "ข้อจำกัด")], [
    [t("Rows in the Records grid", "แถวในตารางรายการข้อมูล"), t("500, in no fixed order", "500 แถว ไม่เรียงลำดับตายตัว")],
    [t("Values offered in Job / Product lists", "ค่าในรายการใบสั่งงาน/ผลิตภัณฑ์"), t("300 (you can still type any value)", "300 ค่า (ยังพิมพ์ค่าใดก็ได้)")],
    [t("Container cards per page", "การ์ดต่อหน้า"), t("up to 20, fewer on a small window", "สูงสุด 20 น้อยกว่านั้นหากหน้าต่างเล็ก")],
    [t("Error log", "บันทึกข้อผิดพลาด"), t("last 500 entries, memory only", "500 รายการล่าสุด เก็บในหน่วยความจำเท่านั้น")],
    [t("Activity log", "บันทึกกิจกรรม"), t("one file per day in the <code>logs</code> folder; never deleted automatically", "หนึ่งไฟล์ต่อวันในโฟลเดอร์ <code>logs</code> ไม่ถูกลบอัตโนมัติ")],
    [t("Serial totals refresh", "การอัปเดตยอดรหัสซีเรียล"), t("about every 10 seconds", "ประมาณทุก 10 วินาที")],
])}
<h3>{t("Keys", "แป้นพิมพ์")}</h3>
{table([t("Key", "แป้น"), t("Where", "ที่ไหน"), t("Does", "ผล")], [
    ["<kbd>Enter</kbd>", t("Value box (filters)", "ช่องค่า (ตัวกรอง)"), t("Runs the search", "ค้นหา")],
    ["<kbd>F2</kbd> / " + t("double-click", "ดับเบิลคลิก"), t("Grid cell", "เซลล์ในตาราง"), t("Edits the cell", "แก้ไขเซลล์")],
    ["<kbd>Enter</kbd>", t("Rename / Delete dialogs", "หน้าต่างเปลี่ยนรหัส/ลบ"), t("Looks the serial up; never confirms", "ค้นหารหัส ไม่ยืนยันการทำรายการ")],
    ["<kbd>Enter</kbd>", "Report damage", t("Reports the serial immediately", "รายงานรหัสทันที")],
    ["<kbd>Alt</kbd>+<kbd>←</kbd> / <kbd>→</kbd>", t("Container manager", "จัดการบรรจุภัณฑ์"), t("Back / Forward", "ย้อนกลับ / ไปข้างหน้า")],
])}
<h3>{t("Label glossary: English ↔ Thai", "คำศัพท์บนหน้าจอ: อังกฤษ ↔ ไทย")}</h3>
{table([t("English", "อังกฤษ"), t("Thai", "ไทย")], [[esc(en), esc(thv)] for en, thv in [
    LABELS[k] for k in ("records", "containers", "filters", "day", "month", "year", "product", "job", "category", "tag", "value", "search", "clear",
                        "columns", "hide_filters", "show_filters", "del", "save", "cancel", "log", "rename_c", "delete_c", "open_box", "view_records",
                        "refresh", "show_all", "show_all_records", "unit", "display", "inner", "carton", "serial_no", "roll_no", "source_id", "target_id", "unassigned")
]])}
""")

    # ---------------------------------------------------------------- page
    toc = "".join(f'<li><a href="#{cid}">{i}. {esc(title)}</a></li>' for i, (cid, title, _b, _p) in enumerate(chapters, start=1))
    body = ""
    for i, (cid, title, content, pb) in enumerate(chapters, start=1):
        body += f'<section class="chapter{" pb" if pb and i > 1 else ""}" id="{cid}"><h2><span class="num">{i}.</span>{esc(title)}</h2>{content}</section>'

    other_href, other_label = ("manual.th.html", "ภาษาไทย (Thai)") if not th else ("manual.html", "English")
    title = t("DataRework User Manual", "คู่มือการใช้งาน DataRework")
    doc = f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>{CSS}</style></head>
<body><div class="layout">
<nav class="toc"><div class="brand">DataRework</div><div class="sub">{t("User manual", "คู่มือการใช้งาน")}</div>
<ol>{toc}</ol>
<div class="langswitch noprint"><a href="{other_href}">🌐 {other_label}</a></div></nav>
<main><div class="paper">
<header class="cover"><div class="kicker">Production Rework</div><h1>{esc(title)}</h1>
<p class="lead">{t("How to use every function of DataRework.exe — signing in, searching records, correcting data, managing containers and reporting damage.", "วิธีใช้งานทุกฟังก์ชันของ DataRework.exe — การเข้าสู่ระบบ การค้นหาข้อมูล การแก้ไขข้อมูล การจัดการบรรจุภัณฑ์ และการแจ้งความเสียหาย")}</p>
<p class="meta">{t("Edition", "ฉบับ")}: {t("English", "ภาษาไทย")} · {t("Matches the application as of", "ตรงกับโปรแกรมเวอร์ชัน")} {BUILD_INFO}<br>
{t("Screenshots use sample data, not real production records.", "ภาพหน้าจอใช้ข้อมูลตัวอย่าง ไม่ใช่ข้อมูลการผลิตจริง")}</p></header>
{body}
<footer class="end">{t("DataRework user manual", "คู่มือการใช้งาน DataRework")} · {BUILD_INFO}. {t("Generated from <code>docs/manual-src</code> (run <code>build_manual.py</code> to regenerate).", "สร้างจาก <code>docs/manual-src</code> (รัน <code>build_manual.py</code> เพื่อสร้างใหม่)")}</footer>
</div></main></div></body></html>"""
    return doc
