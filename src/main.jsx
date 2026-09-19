import React from 'react'
import ReactDOM from 'react-dom/client'
import { Search, MapPin, ExternalLink, Utensils, X } from 'lucide-react'
import './styles.css'

const DATA_URL = './data/restaurants.json'

function App() {
  const [items, setItems] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [query, setQuery] = React.useState('')
  const [prefecture, setPrefecture] = React.useState('すべて')
  const [city, setCity] = React.useState('すべて')
  const [genre, setGenre] = React.useState('すべて')
  const [tag, setTag] = React.useState('すべて')
  const [sort, setSort] = React.useState('name')

  React.useEffect(() => {
    fetch(DATA_URL)
      .then(r => {
        if (!r.ok) throw new Error('データの読み込みに失敗しました')
        return r.json()
      })
      .then(setItems)
      .finally(() => setLoading(false))
  }, [])

  const prefectures = React.useMemo(() => {
    const counts = new Map()
    items.forEach(x => {
      const p = (x.prefecture || '').trim()
      if (p) counts.set(p, (counts.get(p) || 0) + 1)
    })
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0], 'ja'))
  }, [items])

  const cities = React.useMemo(() => {
    const counts = new Map()
    items.forEach(x => {
      if (prefecture !== 'すべて' && x.prefecture !== prefecture) return
      const c = (x.city || '').trim()
      if (c) counts.set(c, (counts.get(c) || 0) + 1)
    })
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0], 'ja'))
  }, [items, prefecture])

  React.useEffect(() => {
    if (city !== 'すべて' && !cities.some(([c]) => c === city)) {
      setCity('すべて')
    }
  }, [cities, city])

  const genres = React.useMemo(() => {
    const counts = new Map()
    items.forEach(x => counts.set(x.genre || '未分類', (counts.get(x.genre || '未分類') || 0) + 1))
    return [...counts.entries()].sort((a,b) => b[1]-a[1])
  }, [items])

  const tags = React.useMemo(() => {
    const counts = new Map()
    items.flatMap(x => x.tags || []).forEach(t => counts.set(t, (counts.get(t)||0)+1))
    return [...counts.entries()].sort((a,b) => b[1]-a[1]).slice(0, 30)
  }, [items])

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    const result = items.filter(x => {
      const text = [
        x.name,
        x.memo,
        x.comment,
        x.prefecture,
        x.city,
        x.address,
        x.country,
        ...(x.tags || [])
      ].filter(Boolean).join(' ').toLowerCase()

      return (!q || text.includes(q)) &&
        (prefecture === 'すべて' || x.prefecture === prefecture) &&
        (city === 'すべて' || x.city === city) &&
        (genre === 'すべて' || x.genre === genre) &&
        (tag === 'すべて' || (x.tags || []).includes(tag))
    })

    return [...result].sort((a,b) => {
      if (sort === 'genre') {
        return (a.genre || '').localeCompare(b.genre || '', 'ja') || a.name.localeCompare(b.name, 'ja')
      }
      if (sort === 'prefecture') {
        return (a.prefecture || '').localeCompare(b.prefecture || '', 'ja') ||
          (a.city || '').localeCompare(b.city || '', 'ja') ||
          a.name.localeCompare(b.name, 'ja')
      }
      return a.name.localeCompare(b.name, 'ja')
    })
  }, [items, query, prefecture, city, genre, tag, sort])

  const reset = () => {
    setQuery('')
    setPrefecture('すべて')
    setCity('すべて')
    setGenre('すべて')
    setTag('すべて')
    setSort('name')
  }

  const active = query || prefecture !== 'すべて' || city !== 'すべて' || genre !== 'すべて' || tag !== 'すべて'

  return <div className="app">
    <header className="hero">
      <div className="brand"><span className="logo"><Utensils size={22}/></span><div><h1>メシウマ</h1><p>Google Mapsに保存した店を、ちゃんと探せるリストに。</p></div></div>
      <div className="stat"><strong>{items.length.toLocaleString()}</strong><span>SPOTS</span></div>
    </header>

    <main>
      <section className="controls">
        <div className="search">
          <Search size={18}/>
          <input
            value={query}
            onChange={e=>setQuery(e.target.value)}
            placeholder="店名・都道府県・市区町村・住所・メモ・タグから検索"
          />
          {query && <button onClick={()=>setQuery('')}><X size={16}/></button>}
        </div>

        <div className="controlRow">
          <label>都道府県
            <select value={prefecture} onChange={e => { setPrefecture(e.target.value); setCity('すべて') }}>
              <option value="すべて">すべて</option>
              {prefectures.map(([p,c]) => <option key={p} value={p}>{p} ({c})</option>)}
            </select>
          </label>

          <label>市区町村
            <select value={city} onChange={e=>setCity(e.target.value)}>
              <option value="すべて">すべて</option>
              {cities.map(([c,n]) => <option key={c} value={c}>{c} ({n})</option>)}
            </select>
          </label>

          <label>ジャンル
            <select value={genre} onChange={e=>setGenre(e.target.value)}>
              <option value="すべて">すべて</option>
              {genres.map(([g,c])=><option key={g} value={g}>{g} ({c})</option>)}
            </select>
          </label>

          <label>タグ
            <select value={tag} onChange={e=>setTag(e.target.value)}>
              <option value="すべて">すべて</option>
              {tags.map(([t,c])=><option key={t} value={t}>{t} ({c})</option>)}
            </select>
          </label>

          <label>並び順
            <select value={sort} onChange={e=>setSort(e.target.value)}>
              <option value="name">店名</option>
              <option value="genre">ジャンル</option>
              <option value="prefecture">都道府県・市区町村</option>
            </select>
          </label>

          {active && <button className="reset" onClick={reset}>リセット</button>}
        </div>
      </section>

      <section className="genreChips">
        <button className={genre==='すべて'?'active':''} onClick={()=>setGenre('すべて')}>すべて <span>{items.length}</span></button>
        {genres.map(([g,c])=><button key={g} className={genre===g?'active':''} onClick={()=>setGenre(g)}>{g} <span>{c}</span></button>)}
      </section>

      <div className="resultHead">
        <strong>{loading ? '読み込み中…' : `${filtered.length.toLocaleString()} 件`}</strong>
        <div>
          {prefecture !== 'すべて' && <span>{prefecture}</span>}
          {city !== 'すべて' && <span>{city}</span>}
          {genre !== 'すべて' && <span>{genre}</span>}
        </div>
      </div>

      <section className="grid">
        {filtered.map((x,i)=><article className="card" key={`${x.url}-${i}`}>
          <div className="cardTop">
            <span className="genre">{x.genre || '未分類'}</span>
            {x.tags?.length>0 && <span className="tags">{x.tags.slice(0,2).map(t=>`#${t}`).join(' ')}</span>}
          </div>
          <h2>{x.name}</h2>
          {(x.prefecture || x.city) && (
            <p className="location">
              <MapPin size={15}/>
              {[x.prefecture, x.city].filter(Boolean).join(' ')}
            </p>
          )}
          {x.memo && <p className="memo">{x.memo}</p>}
          {x.comment && <p className="comment">{x.comment}</p>}
          <a href={x.url} target="_blank" rel="noreferrer"><MapPin size={16}/> Google Mapsで開く <ExternalLink size={14}/></a>
        </article>)}
      </section>

      {!loading && filtered.length===0 && <div className="empty">条件に合う店がありません。</div>}
    </main>

    <footer>MESHI UMA / Google Maps Saved Places Viewer</footer>
  </div>
}

ReactDOM.createRoot(document.getElementById('root')).render(<React.StrictMode><App/></React.StrictMode>)
