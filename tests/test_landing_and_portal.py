import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_landing_page_renders_successfully():
    """Verifica que la landing page en / responda 200 OK y contenga los elementos clave."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")
        assert response.status_code == 200
        html = response.text
        # Verificación de marca y logos
        assert "EduAgro" in html
        # Verificación del Hero y propuesta de valor
        assert "Productor Agropecuario" in html
        # Verificación del Visor Satelital en primer plano
        assert "Monitoreo Satelital" in html or "Satelital" in html
        assert "El Triángulo" in html
        assert "Soja 1ra" in html
        # Verificación de mercado y cotizaciones explícitas en su propia sección
        assert "DÓLAR OFICIAL CAC" in html
        assert 'id="mercado"' in html
        # Verificación de que no está el manual PDF familiar en la landing
        assert "Manual Didáctico (PDF)" not in html
        # Verificación de menú hamburguesa mobile
        assert 'id="mobile-menu-btn"' in html
        assert 'id="mobile-menu-drawer"' in html
        # Verificación de los showcases de módulos
        assert "showcase-modulos" in html
        assert "Motor Precio Neto" in html
        assert "Silobolsas" in html
        assert "Modo Camioneta" in html

@pytest.mark.asyncio
async def test_portal_unauthenticated_redirects_to_login():
    """Verifica que /portal sin sesión redirija a /login?next=/portal."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/portal", follow_redirects=False)
        assert response.status_code == 303
        assert "/login?next=/portal" in response.headers["location"]
