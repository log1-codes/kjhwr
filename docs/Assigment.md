1. Problem setting

Consider that you are a product developer developing and delivering a customized software product to a client. A product manager has given you some broad context, directions, and requirements as below. You need to understand it, do additional learning and information gathering to gain sufficient knowledge of the domain, then develop the first version of the product based on it. You also need to:

- present and pitch the product to the client

- explain the software design and implementation to an internal technical lead reviewing the work


2. Requirement 

(from the product manager)

The client is an energy utility in the UK. They need to buy electricity from the wholesale market to serve their consumers. The specific team (that we are pitching the software to) is responsible for buying required power from the UK day-ahead market. More specifically, to meet their consumers’ electricity demand, they need to understand how much power needs to be additionally procured (e.g., from thermal plants) beyond the generation available from renewable sources like wind. The power generation from renewable sources is weather-dependent, and the power purchase decisions from the day-ahead market need to be made one day before the delivery day. Hence, they need to rely on renewable generation forecasts when making decisions. 

Using our web app product, they need to:

1. Clearly understand the latest renewable generation forecasts available when they need to make decisions on buying from the day-ahead market

2. Evaluate the accuracy of the renewable generation forecasts quantitatively, so that they can make their decisions considering the quantified error

To limit the scope of this challenge, for the above 2 purposes, we consider the national level generation of actuals and forecasts of wind power available from elexon alone (no other data beyond this).

~~***2.1 Actual generation**

~~***The actual generation data for this is available at [https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream). Please consider values corresponding to “fuelType” “WIND”. Some relevant fields:**


- ~~***"startTime": the target time (resolution of 30 minutes)**

- ~~***“generation”: generated wind power**


~~***2.2 Forecasted generation**

~~***The forecasts are available at [https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream). Relevant fields:**

- ~~***“startTime”: similar to the "startTime" field in the actuals dataset**

- ~~***"publishTime": the time at which the forecast was created**

- ~~***“generation": similar to the "generation" field in the actuals dataset**


~~***Please consider data relevant only for purchase decisions to be made in January 2026. **

~~***Please build the application using React for front-end and Python for backend. You are free to use AI tools to assist with building this application (please mention it explicitly in the README if you’ve used AI tools). Please use docker. Please deploy the sample application in vercel or heroku. **

~~***Please do not spend more than 16 hours on this assignment. There is no deadline for submission. However, the earlier the better.**


3. Deliverables

3.1 Video demo

~~***Please create an unlisted youtube video ([guide](https://sites.uab.edu/apex/for-mph-students/youtube-video/)) as explained below. **

~~***The video needs to have 2 parts:**

~~***Part 1: Assume that you’re presenting the portal and analysis to the customer as the output of a pilot project you’ve done for them. The goal is to impress them. Please include a max 5-minute-long initial overview. **

~~***Part 2: Assume that you’re showing the work to the tech load for his/her review. You need to explain the architecture, design, analysis, code base, and key development practices. The goal is to make review easy and to provide clear knowledge transfer too.  Please include a max 5-minute-long initial overview.**

~~***Please limit the video to a maximum of 10 minutes.**

~~***Our evaluation will start with the video. Hence, please don’t submit without this video.**

***3.2 Repo**

~~***Please create a public github repo (with an anonymous repo name e.g., a random string like “kjhwr”) to submit your code. Please include a README containing:**

- ~~***Details of the files and directories present**

- ~~***How to start the application**

- ~~***Link to the vercel/heroku app**

  
***3.3 Submit form**


***Please submit all the details in this form: [https://forms.cloud.microsoft/r/FTX6K2bbnU**](https://forms.cloud.microsoft/r/FTX6K2bbnU)


Please open each URL you’re submitting as part of the form in incognito mode and verify that sufficient access is available for them.
