import json,re,html,sys
d=json.load(open(sys.argv[1]))
v=d['value']
c=v.get('content',{})
body=c.get('content') if isinstance(c,dict) else c
if body is None:
    body=json.dumps(v,ensure_ascii=False)
t=re.sub(r'<script.*?</script>|<style.*?</style>','',body,flags=re.S)
t=re.sub(r'<br\s*/?>|</p>|</li>|</tr>|</pre>|</h\d>','\n',t)
txt=html.unescape(re.sub(r'<[^>]+>','',t))
txt=re.sub(r'\n\s*\n+','\n',txt)
print('TITLE:',v.get('title'),'| updated:',v.get('updatedDate') or v.get('updateTime') or v.get('publishTime'))
open(sys.argv[1]+'.txt','w').write(txt)
print(len(txt))
