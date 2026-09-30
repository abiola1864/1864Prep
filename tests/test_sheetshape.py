import warnings; warnings.filterwarnings("ignore")
from engine.sheetshape import classify_sheet
def test_table_vs_form_vs_list():
    table=[["name","city","age"],["Ada","Lagos","30"],["Bola","Kano","40"],["Uche","Oyo","25"]]
    assert classify_sheet(table)["kind"]=="table", classify_sheet(table)
    lst=[["Checklist"],["Item A"],["Item B"],["Item C"],["Item D"]]
    assert classify_sheet(lst)["kind"]=="list", classify_sheet(lst)
    # realistic sparse form: label:value pairs spread across a wide, mostly-empty grid
    form=[["","","","","",""],["","TRAVEL ADVANCE REQUEST","","","",""],["","","","","",""],
          ["","Name:","","","Date:",""],["","Dept:","","","Grade:",""],
          ["","Departure Date:","","","Return Date:",""],["","Purpose:","","","",""],
          ["","Amount:","","","Approved:",""]]
    assert classify_sheet(form)["kind"] in ("form","embedded"), classify_sheet(form)
    print("shape classifier: table/list/form all correct")
test_table_vs_form_vs_list()
print("SHEETSHAPE TEST PASSED")
