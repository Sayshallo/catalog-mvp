async function getProducts() {
    const res = await fetch(
        `${process.env.API_URL}/api/products`, {cache: "no-store"},
    );

    if (!res.ok) return [];
    return res.json();
}

export default async function CatalogPage() {
    const products = await getProducts()

    return (
        <main>
            <h1>Catalog</h1>
            <ul>
                {products.map((p: any) => (
                    <li key={p.id} style={{ marginBottom: '20px', borderBottom: '1px solid #eee', paddingBottom: '10px'}}>
                        <strong>{p.title}</strong>
                        {p.image_url && (
                            <img src={`/api/products/${p.id}/image`} alt={p.title} style={{ maxWidth: '100px', marginTop: '5px' }} />
                        )}
                    </li>
                ))}
            </ul>
        </main>
    );
}