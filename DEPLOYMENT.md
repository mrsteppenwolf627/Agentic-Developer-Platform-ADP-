# Deployment

## Backend: Railway o Render

1. Crear un servicio nuevo apuntando al repositorio.
2. Definir `DATABASE_URL` con el DSN PostgreSQL productivo.
3. Definir claves de modelo si se habilitan llamadas LLM reales:
   - `ANTHROPIC_API_KEY`
   - `GOOGLE_API_KEY`
   - `OPENAI_API_KEY`
4. Comando recomendado:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Frontend: Vercel

1. Importar el repositorio en Vercel.
2. Configurar `VITE_API_URL` o ajustar el cliente HTTP para apuntar al backend desplegado.
3. Build command recomendado:

```bash
npm install && npm run build
```

## GitHub Secrets para CI/CD

- `CODECOV_TOKEN`
- `DATABASE_URL`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `OPENAI_API_KEY`
- Cualquier token adicional de Vercel, Railway o Render usado por su pipeline real

## Post-deploy

Verificar:

```bash
curl https://<backend-url>/health
```

La respuesta esperada debe incluir `status=ok`.
