import json, sys
sys.path.insert(0, ".")
from p03 import db, retrieve
d = json.load(open("evals/dev_queries.json", encoding="utf-8"))
con = db.connect()
for k in ("answerable", "unanswerable"):
    print(k)
    for q in d[k]:
        print("  %.3f  %s" % (retrieve.search(con, "mirlo", q, 1)[0]["score"], q))
