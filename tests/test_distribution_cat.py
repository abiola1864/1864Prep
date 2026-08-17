
import warnings; warnings.filterwarnings("ignore"); import pandas as pd
from engine.distribution import distribution_profile
df=pd.DataFrame({"state":["Lagos","Kano","Lagos","Oyo","Lagos","Kano","Lagos","Kano"],
                 "score":[10,11,12,13,900,11,10,9]})
prof={d["column"]:d for d in distribution_profile(df)}
assert prof["state"]["kind"]=="categorical"
assert prof["state"]["distinct"]==3
assert prof["state"]["top"][0]["value"]=="Lagos" and prof["state"]["top"][0]["count"]==4
assert prof["score"]["kind"]=="numeric" and prof["score"]["outliers"]>=1
print("distribution categorical wow OK")
