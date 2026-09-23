import sys,re,html
from html.parser import HTMLParser
class P(HTMLParser):
    def __init__(s):
        super().__init__(); s.out=[]; s.skip=0
    def handle_starttag(s,t,a):
        if t in ('script','style'): s.skip+=1
        if t in ('p','div','tr','li','h1','h2','h3','h4','br','pre','dt','dd','table'): s.out.append('\n')
        if t in ('td','th'): s.out.append(' | ')
    def handle_endtag(s,t):
        if t in ('script','style'): s.skip-=1
        if t in ('p','div','tr','li','h1','h2','h3','h4','pre','dt','dd'): s.out.append('\n')
    def handle_data(s,d):
        if not s.skip: s.out.append(d)
p=P(); p.feed(open(sys.argv[1],encoding='utf-8',errors='ignore').read())
txt=''.join(p.out); txt=re.sub(r'[ \t]+',' ',txt); txt=re.sub(r'\n\s*\n+','\n',txt)
open(sys.argv[2],'w').write(txt)
