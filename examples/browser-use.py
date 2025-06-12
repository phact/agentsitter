import asyncio
from dotenv import load_dotenv
load_dotenv()
from browser_use import Agent
from langchain_openai import ChatOpenAI
from browser_use import Agent, BrowserSession, BrowserProfile, BrowserContext, BrowserConfig
import os
from playwright._impl._api_structures import ProxySettings

token = os.environ.get("AGENTSITTER_TOKEN","")

async def main():

    # a profile is a static, flat collection of config parameters
    browser_profile = BrowserProfile(
        channel="chrome",
        headless=False,
        #headless=True,
        disable_security=False,
        chromium_sandbox=False,
        proxy=ProxySettings(server="http://localhost:8080", username=token, password="")
    )

    # a session is a live connection to a real browser running somewhere
    browser_session = BrowserSession(
        browser_profile=browser_profile,
    )

    # you can optionally start a session and use it outside an Agent, otherwise Agent will automatically start it
    await browser_session.start()

    llm = ChatOpenAI(model="gpt-4o")

    agent = Agent(
        task='log into hacker news',
        browser_session=browser_session,
        llm=llm
    )
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
