class ClaudeProvider:
    def __init__(self, client, model: str) -> None:
        self._client = client
        self._model = model

    async def complete(
        self, system_prompt: str, user_prompt: str, **kwargs
    ) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=kwargs.get("max_tokens", 4096),
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
