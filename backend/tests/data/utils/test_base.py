from backend.fundmate.data.utils import base


def test_parse_headers():
    h_str = """Accept: application/json, text/javascript, */*; q=0.01
Accept-Encoding: gzip, deflate, br
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7
Connection: keep-alive
Content-Length: 0
Cookie: kbzw_r_uname=%E8%A5%BF%E9%A3%8E%E4%B8%8D%E7%98%A6; kbz_newcookie=1; kbzw__Session=a295sqg2agsgc6dqgd786nk613;""" \
            """Hm_lvt_164fe01b1433a19b507595a43bf58262=1622536736,1622596667,1622686815,1623044428;""" \
            """kbzw__user_login=7Obd08_P1ebax9aXXwc1ShoFVzDuV_kamrCW6c3q1e3Q6dvR1YyglaSx25mv0trD15nZ3KTbwqHG16""" \
            """mqmbKirpfbw9nb2Jmcndbd3dPGpJ-pm6uSqJiupbaxv9Gkwtjz1ePO15CspaOYicfK4t3k4OyMxbaWkqelo7OBx8rir6m""" \
            """kmeStlp-BuOfj5MbHxtbE3t2ooaqZpJStl5vDqcSuwKWV1eLX3IK9xtri4qGBs8nm6OLOqKWokKaPq6uqqo-nmJTM1s""" \
            """_a3uCRq5SupaaugbXF26iumqecpZqslaWrpA..;""" \
            """Hm_lpvt_164fe01b1433a19b507595a43bf58262=1623296705
DNT: 1
Host: www.jisilu.cn
Origin: https://www.jisilu.cn
Referer: https://www.jisilu.cn/
sec-ch-ua: " Not;A Brand";v="99", "Microsoft Edge";v="91", "Chromium";v="91"
sec-ch-ua-mobile: ?0
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77""" \
            """ Safari/537.36 Edg/91.0.864.41
X-Requested-With: XMLHttpRequest
"""
    result = base.parse_headers(h_str)
    assert result == {
        'Accept':
        'application/json, text/javascript, */*; q=0.01',
        'Accept-Encoding':
        'gzip, deflate, br',
        'Accept-Language':
        'zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7',
        'Connection':
        'keep-alive',
        'Content-Length':
        '0',
        'Cookie':
        'kbzw_r_uname=%E8%A5%BF%E9%A3%8E%E4%B8%8D%E7%98%A6; kbz_newcookie=1; '
        'kbzw__Session=a295sqg2agsgc6dqgd786nk613;Hm_lvt_164fe01b1433a19b507595a43bf58262'
        '=1622536736,1622596667,1622686815,1623044428;kbzw__user_login=7Obd08_P1ebax9aXXwc1Sho'
        'FVzDuV_kamrCW6c3q1e3Q6dvR1YyglaSx25mv0trD15nZ3KTbwqHG16mqmbKirpfbw9nb2Jmcndbd3dPGpJ'
        '-pm6uSqJiupbaxv9Gkwtjz1ePO15CspaOYicfK4t3k4OyMxbaWkqelo7OBx8rir6mkmeStlp-BuOfj5MbH'
        'xtbE3t2ooaqZpJStl5vDqcSuwKWV1eLX3IK9xtri4qGBs8nm6OLOqKWokKaPq6uqqo-nmJTM1s_'
        'a3uCRq5SupaaugbXF26iumqecpZqslaWrpA..;Hm_lpvt_164fe01b1433a19b507595a43bf5'
        '8262=1623296705',
        'DNT':
        '1',
        'Host':
        'www.jisilu.cn',
        'Origin':
        'https://www.jisilu.cn',
        'Referer':
        'https://www.jisilu.cn/',
        'sec-ch-ua':
        '" Not;A Brand";v="99", "Microsoft Edge";v="91", "Chromium";v="91"',
        'sec-ch-ua-mobile':
        '?0',
        'Sec-Fetch-Dest':
        'empty',
        'Sec-Fetch-Mode':
        'cors',
        'Sec-Fetch-Site':
        'same-origin',
        'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)'
        ' Chrome/91.0.4472.77 Safari/537.36 Edg/91.0.864.41',
        'X-Requested-With':
        'XMLHttpRequest'
    }
