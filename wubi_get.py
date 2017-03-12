#!/usr/bin/env python
# coding=utf-8

# 感谢此网站提供了规范的汉字字符表。http://xh.5156edu.com/page/z6211m4474j19255.html
# 感谢此网站提供了五笔编码查询及拆分结果。http://www.chaiwubi.com/
# 本工具只提供最常用的86版五笔的相关信息，98，06版需要自己用相同的方法添加。
# 特别声明，本工具只用于方便五笔本地查询和学习使用，请勿用于商业用途，误用带来的后果由使用者负责。
import urllib
import urllib2
import random
import bs4
import os
import time
import yaml
import codecs
from threading import Thread
from threading import Lock
from Queue import Queue


UA_POOL = [
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36',
#'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; .NET CLR 3.0.04506)',
#    'Mozilla/5.0(WindowsNT6.1;rv:2.0.1)Gecko/20100101Firefox/4.0.1',
#    'Opera/9.80(WindowsNT6.1;U;en)Presto/2.8.131Version/11.11'
]

POOL_IMG = set()
CUR_PATH = os.path.split(os.path.realpath(__file__))[0]
chs_lock = Lock()
CHS_WUBI_DICT = {}
page_io_queue = Queue()
resource_io_queue = Queue()
MAX_PAGE_IO = 8
MAX_RES_IO = 4
TASK_TYPE_PAGE = 1
TASK_TYPE_RES = 0

#从文件中读取汉字，放到队列中。
def load_chinese_dict(file_name):
    with codecs.open(file_name, 'r', 'utf8') as f:
        contents = f.readlines()
        contents = ','.join(contents)
        contents = list(contents)[:-1]
        for c in contents:
            page_io_queue.put(c.encode("utf8"))

def wubi_query(word, type='查单字'):
    query_url = 'http://www.chaiwubi.com/bmcx/'
    form = {
        'wz': word,
        'select_value': type,
    }
    post_data = urllib.urlencode(form)
    req = urllib2.Request(query_url, post_data)
    req.add_header('Referer', 'http://www.chaiwubi.com/bmcx/')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    req.add_header('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8')
    #req.add_header('Accept-Encoding', 'gzip, deflate')
    req.add_header('Accept-Language', 'zh-CN,zh;q=0.8,en-US;q=0.6,en;q=0.4')
    req.add_header('User-Agent', UA_POOL[random.randint(0, len(UA_POOL) -1)])
    try:
        response = urllib2.urlopen(req)
    except urllib2.URLError, e:
        return None
    except urllib2.HTTPError, e:
        return None

    ret = response.read()
    return ret

def extract_info(text):
    soup = bs4.BeautifulSoup(text, 'lxml')
    content_table_rows = soup.select('.dw-bmcx tr')
    if len(content_table_rows) < 2:
        return False

    content_86 = content_table_rows[0]
    tds = content_86.find_all('td')
    code = tds[0].a.text.strip()
    code1 = tds[2].strong.text
    code2 = tds[3].strong.text
    code3 = tds[4].strong.text
    code4 = tds[5].strong.text
    word_root = []
    for img in tds[6].find_all('img'):
        word_root.append(img['src'])
        if img['src'] in POOL_IMG: 
            continue
        POOL_IMG.add(img['src'])
        resource_io_queue.put(img['src'])

    content_98 = content_table_rows[1]
    tds = content_98.find_all('td')
    word_split = tds[6]
    word_split_img = word_split.img['src']
    resource_io_queue.put(word_split_img)
    chs_lock.acquire()
    CHS_WUBI_DICT[code.encode('utf8')] = [code1, code2, code3, code4, word_root, word_split_img]
    chs_lock.release()

    print('result is %s %s, %s, %s, %s, root %s, img %s' %(code, code1, code2, code3, code4, word_root, word_split_img))
    return True

def download(url, filename):
    try:
        f = urllib2.urlopen(url.encode('utf8'))
        with open(filename,"wb") as code:
            code.write(f.read())
    except:
        print('%s download failed' %url)
        return

class WubiIOThread(Thread):
    def __init__(self, run_type):
        Thread.__init__(self)
        self.run_type = run_type

    def run(self):
        conntent_type = 'resource' if self.run_type == TASK_TYPE_RES else 'page' 
        print('%s download thread is runing.' %conntent_type)
        if self.run_type == TASK_TYPE_PAGE:
            self.do_page_downlaod()
            print('page download thread task finished start help do resource download task.')

        self.do_resource_downlaod()
        print('%s download thread is finished.' %conntent_type)

    # 执行下载页面任务和分析页面任务，因为页面分析任务比较小，所以放在一块。
    def do_page_downlaod(self):
        while not page_io_queue.empty():
           word = page_io_queue.get()
           if not word:
               return
           #print('get %d word %s'%(i, word))
           ret = wubi_query(word)
           if ret:
               if not extract_info(ret):
                   print('can not find complete information for %s.' %word)
           else:
               print('request for %s failed' %word)
           time.sleep(1)

    # 下载字根或拆字和图片
    def do_resource_downlaod(self):
        time.sleep(20)
        while not resource_io_queue.empty():
            url = resource_io_queue.get()
            print('start download url' + url)
            if not url:
                print('no url has found, will return')
                return
            item_parts = url.split('/')
            file_part = item_parts[-1]
            folder_part = item_parts[-2]
            post_fix = file_part.split('.')[-1]
            if post_fix == 'gif' or post_fix == 'bmp' or post_fix == 'png':
                folder = os.path.join(CUR_PATH, folder_part)
                if not os.path.exists(folder):
                    os.mkdir(folder)
                download(url, os.path.join(folder, file_part))
            time.sleep(1)

if __name__ == '__main__':
    load_chinese_dict('chinese.txt')
    threads = []
    for i in range(0, MAX_PAGE_IO):
        t = WubiIOThread(i / MAX_RES_IO)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    with codecs.open('chs_dict.yml', 'w', 'utf8') as f:
        yaml.dump(CHS_WUBI_DICT, f, allow_unicode=True)
