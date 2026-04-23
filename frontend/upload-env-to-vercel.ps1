# Leer .env y subir cada variable a Vercel

$envFile = ".env"
$lines = Get-Content $envFile

foreach ($line in $lines) {
    if ($line -match "^([^=]+)=(.*)$") {
        $key = $matches[1]
        $value = $matches[2]
        
        Write-Host "Subiendo: $key"
        
        # Ejecutar: vercel env add KEY VALUE
        echo $value | vercel env add $key
    }
}

Write-Host "✅ Todas las variables subidas"