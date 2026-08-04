# Frontend (Angular 19)

Aplicación de cliente del **Zebra Invoice Extractor**: carga de facturas por drag & drop,
llamada a la API REST del backend y visualización estructurada del resultado.

La documentación completa (instalación, configuración y uso) está en el
[README principal](../README.md).

Comandos:

```powershell
npm install      # instalar dependencias
ng serve         # arrancar en http://localhost:4200
ng build         # build de producción en dist/
```

El dev server redirige `/api` a `http://localhost:8000` mediante `proxy.conf.json`.
