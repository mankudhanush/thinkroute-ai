import asyncio
import litellm

async def main():
    try:
        response = await litellm.acompletion(
            model='cloudflare/@cf/meta/llama-3.1-8b-instruct',
            messages=[{'role': 'user', 'content': 'hi'}],
            api_key='fake',
            api_base='https://api.cloudflare.com/client/v4/accounts/test_account/ai/run/'
        )
    except Exception as e:
        print('Error:', e)

asyncio.run(main())
