"""Export the actual PostgreSQL tables and foreign keys, without application data."""
import json
from import_dataset import connect
with connect() as c:
    tables=c.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN ('identity','ingestion','content','learning','intelligence') ORDER BY schemaname,tablename").fetchall()
    links=c.execute("SELECT ns.nspname,t.relname,nt.nspname,p.relname,k.conname FROM pg_constraint k JOIN pg_class t ON t.oid=k.conrelid JOIN pg_namespace ns ON ns.oid=t.relnamespace JOIN pg_class p ON p.oid=k.confrelid JOIN pg_namespace nt ON nt.oid=p.relnamespace WHERE k.contype='f' AND ns.nspname IN ('identity','ingestion','content','learning','intelligence') ORDER BY 1,2,3,4").fetchall()
    version=c.execute('SELECT version_num FROM alembic_version').fetchone()[0]
lines=['# Current database schema',f'Live migration: `{version}`. {len(tables)} tables. Arrows point from referencing child to referenced parent.','', '```mermaid','flowchart LR']
for schema in sorted({s for s,t in tables}):
    lines.append(f'  subgraph {schema}["{schema}"]')
    for s,t in tables:
        if s==schema: lines.append(f'    {s}_{t}["{t}"]')
    lines.append('  end')
seen=set()
for s,t,ps,pt,name in links:
    edge=(s,t,ps,pt)
    if edge not in seen: lines.append(f'  {s}_{t} --> {ps}_{pt}');seen.add(edge)
lines.extend(['```','','## Foreign keys','', '| Child | Parent | Constraint |','|---|---|---|'])
for s,t,ps,pt,name in links: lines.append(f'| {s}.{t} | {ps}.{pt} | {name} |')
print('\n'.join(lines))
