## Logging

By default, Androguard is verbose in its logging. It uses the loguru package. 

This can be a good thing for working out if a script is running or even for teaching. It can be used to demonstrate the app zip is full of code and why we use Androgurad for teaching. 

You may need to switch it off for performance reasons, such as running batch jobs. 

This can be done by overriding the logger in your own script:

```
from loguru import logger
logger.remove()  # removes all loguru handlers
logger.add(lambda msg: None, level="CRITICAL")
```

We can then add critical back in to capture any messages, breaks, or failures under the critical banner. It seems have a small performance effect as a print stream is not being constantly generated. 