import sys
sys.path.insert(0, ".")
from p03 import db
con = db.connect()
for r in con.execute("select tenant_id,chunk_id,page,text from chunks order by tenant_id,doc_id,chunk_idx"):
    print(r["tenant_id"], r["chunk_id"], "p%d" % r["page"], r["text"])
