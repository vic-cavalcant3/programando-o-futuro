import asyncio, httpx

URL = "https://programando-o-futuro.onrender.com/"  # troca pela URL real

async def cadastrar_e_testar(i):
    async with httpx.AsyncClient(timeout=60) as client:
        # Cadastra
        r = await client.post(f"{URL}/api/auth/cadastro", json={
            "nome": f"Teste Usuario {i}",
            "email": f"teste{i}_{asyncio.get_event_loop().time():.0f}@teste.com",
            "senha": "123456",
            "aceite_lgpd": True,
            "aceite_menor": False
        })
        token = r.json().get("token")
        print(f"👤 Usuário {i} cadastrado")

        headers = {"Authorization": f"Bearer {token}"}
        # Finaliza o teste (vai chamar a IA)
        await client.post(f"{URL}/api/testeinicial/finalizar",
            headers=headers,
            json={"respostas": [{"perguntaId": str(j), "valor": "A"} for j in range(1, 23)]}
        )
        print(f"✅ Usuário {i} finalizou")

async def main():
    # Simula 5 usuários ao mesmo tempo
    await asyncio.gather(*[cadastrar_e_testar(i) for i in range(5)])

asyncio.run(main())