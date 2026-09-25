import json,sys
def text(node):
    out=[]
    if isinstance(node,dict):
        t=node.get('type')
        if t=='text': out.append(node.get('text',''))
        elif t=='codeVoice': out.append('`'+node.get('code','')+'`')
        elif t=='reference': out.append('['+node.get('identifier','').split('/')[-1]+']')
        for k in ('inlineContent','content','items'):
            if k in node: 
                for c in node[k]: out.append(text(c))
        if t in ('paragraph','heading'): out.append('\n')
    elif isinstance(node,list):
        for c in node: out.append(text(c))
    return ''.join(out)
for f in sys.argv[1:]:
    d=json.load(open(f))
    print('=====',f)
    print('ABSTRACT:',text(d.get('abstract',[])))
    for s in d.get('primaryContentSections',[]):
        if s.get('kind')=='content': print(text(s.get('content',[])))
