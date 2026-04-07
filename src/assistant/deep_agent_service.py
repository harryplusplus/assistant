# import uuid

# from assistant.deep_agent import DeepAgent


# class DeepAgentService:
#     def __init__(self, deep_agent: DeepAgent) -> None:
#         self._deep_agent = deep_agent

#     async def invoke(self, prompt: str) -> None:
#         thread_id = str(uuid.uuid7())
#         result = await self._deep_agent.ainvoke(  # pyright: ignore[reportUnknownMemberType]
#             prompt, config={"configurable": {"thread_id": thread_id}}
#         )
#         print(f"Result for thread_id={thread_id}: {result}")
