Tests de integración (guía):

- Pruebas básicas:
  - create_message preview generation with sample payload
  - compute_huella_verifactu -> compare against expected examples (from docs/Veri-Factu...)
  - xml signing (python-xmlsec) -> verify signature structure exists
  - send to preprod (manual) with cert/key -> expect known errors or success

- CI:
  - mock AEAT endpoints for unit tests (responses)
  - integration tests can be gated (only run when env vars provide cert/key and env=preprod)
