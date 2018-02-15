from credentials import Credentials
from wallhaven import Wallhaven, Filter

if __name__ == '__main__':
    c = Credentials()
    if not c.have_creds:
        c.get_login_from_user()

    fltr = Filter.from_url(
            'https://alpha.wallhaven.cc/search?q=&categories=111&'
            'purity=111&topRange=1M&sorting=toplist&order=desc&page=2')

    wallhaven = Wallhaven(fltr)

    count = 0
    limit = 50

    ids = []

    for preview in wallhaven:
        if preview.id in ids:
            raise ValueError('wtf' + preview.id)
        ids.append(preview.id)
        print(f'id: {preview.id}')
        count += 1
        # if count >= limit:
        #     print('breaking early')

    # wr = WallhavenResults(1, fltr, wallhaven.requester)
    # print(wr.soup_total_pages_count)
