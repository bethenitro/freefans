# JMeter Stress Test Guide for Telegram Polling Bot

## Overview
Since your bot uses **polling** (not webhooks), you cannot directly send HTTP requests to your bot. Instead, you need to simulate real user interactions by sending messages through **Telegram's Bot API**.

## Architecture
```
JMeter → Telegram Bot API → Your Bot (polling)
```

Your bot polls Telegram servers for updates, so JMeter will send messages via Telegram's API, and your bot will receive them through its polling mechanism.

---

## JMeter Configuration

### 1. Thread Group Setup

**Right-click Test Plan → Add → Threads (Users) → Thread Group**

Configure:
- **Number of Threads (users)**: `10` (start small, increase gradually)
- **Ramp-Up Period (seconds)**: `10` (1 user per second)
- **Loop Count**: `5` (each user will send 5 messages)
- **Duration**: Leave empty or set to 300 seconds

---

### 2. HTTP Request Defaults (Optional but Recommended)

**Right-click Thread Group → Add → Config Element → HTTP Request Defaults**

Configure:
- **Protocol**: `https`
- **Server Name**: `api.telegram.org`
- **Port**: `443`

---

### 3. User Defined Variables

**Right-click Thread Group → Add → Config Element → User Defined Variables**

Add these variables:
- **BOT_TOKEN**: `YOUR_BOT_TOKEN_HERE` (get from BotFather)
- **CHAT_ID**: `YOUR_TELEGRAM_USER_ID` (your user ID to receive messages)

To get your CHAT_ID:
1. Send a message to your bot
2. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Look for `"from":{"id":123456789}` in the response

---

### 4. HTTP Header Manager

**Right-click Thread Group → Add → Config Element → HTTP Header Manager**

Add:
- **Name**: `Content-Type`
- **Value**: `application/json`

---

### 5. HTTP Request Samplers

Create multiple samplers to test different bot commands:

#### A. Test /start Command

**Right-click Thread Group → Add → Sampler → HTTP Request**

Configure:
- **Name**: `Send /start Command`
- **Protocol**: `https`
- **Server Name**: `api.telegram.org`
- **Method**: `POST`
- **Path**: `/bot${BOT_TOKEN}/sendMessage`

**Body Data** (check "Body Data" tab):
```json
{
  "chat_id": "${CHAT_ID}",
  "text": "/start"
}
```

#### B. Test Creator Search

**Right-click Thread Group → Add → Sampler → HTTP Request**

Configure:
- **Name**: `Search Creator`
- **Protocol**: `https`
- **Server Name**: `api.telegram.org`
- **Method**: `POST`
- **Path**: `/bot${BOT_TOKEN}/sendMessage`

**Body Data**:
```json
{
  "chat_id": "${CHAT_ID}",
  "text": "test_creator_${__threadNum}"
}
```

Note: `${__threadNum}` generates unique values per thread to simulate different users searching for different creators.

#### C. Test /help Command

**Right-click Thread Group → Add → Sampler → HTTP Request**

Configure:
- **Name**: `Send /help Command`
- **Protocol**: `https`
- **Server Name**: `api.telegram.org`
- **Method**: `POST`
- **Path**: `/bot${BOT_TOKEN}/sendMessage`

**Body Data**:
```json
{
  "chat_id": "${CHAT_ID}",
  "text": "/help"
}
```

#### D. Test Random Text Messages

**Right-click Thread Group → Add → Sampler → HTTP Request**

Configure:
- **Name**: `Random Message`
- **Protocol**: `https`
- **Server Name**: `api.telegram.org`
- **Method**: `POST`
- **Path**: `/bot${BOT_TOKEN}/sendMessage`

**Body Data**:
```json
{
  "chat_id": "${CHAT_ID}",
  "text": "Random message ${__Random(1,1000)}"
}
```

---

### 6. Response Assertions (Optional)

**Right-click HTTP Request → Add → Assertions → Response Assertion**

Configure:
- **Apply to**: Main sample only
- **Response Field to Test**: Response Code
- **Pattern Matching Rules**: Equals
- **Patterns to Test**: `200`

---

### 7. Listeners (View Results)

Add these to monitor performance:

#### A. View Results Tree
**Right-click Thread Group → Add → Listener → View Results Tree**
- Shows individual requests/responses
- Useful for debugging

#### B. Summary Report
**Right-click Thread Group → Add → Listener → Summary Report**
- Shows aggregate statistics
- Response times, throughput, error rate

#### C. Graph Results
**Right-click Thread Group → Add → Listener → Graph Results**
- Visual representation of performance

#### D. Response Time Graph
**Right-click Thread Group → Add → Listener → Response Time Graph**
- Shows response times over time

---

## Advanced Configuration

### Using CSV Data for Multiple Users

If you want to test with multiple different chat IDs:

1. Create a CSV file (`test_users.csv`):
```csv
chat_id
123456789
987654321
456789123
```

2. Add **CSV Data Set Config**:
   **Right-click Thread Group → Add → Config Element → CSV Data Set Config**
   
   Configure:
   - **Filename**: `test_users.csv`
   - **Variable Names**: `CHAT_ID`
   - **Recycle on EOF**: `True`
   - **Stop thread on EOF**: `False`

3. Use `${CHAT_ID}` in your HTTP requests

---

### Simulating Callback Queries (Button Clicks)

**Right-click Thread Group → Add → Sampler → HTTP Request**

Configure:
- **Name**: `Simulate Button Click`
- **Method**: `POST`
- **Path**: `/bot${BOT_TOKEN}/sendMessage`

**Body Data**:
```json
{
  "chat_id": "${CHAT_ID}",
  "text": "callback_query_simulation"
}
```

Note: This is simplified. Real callback queries require message IDs and callback data.

---

### Adding Think Time Between Requests

**Right-click HTTP Request → Add → Timer → Constant Timer**

Configure:
- **Thread Delay (milliseconds)**: `2000` (2 seconds between requests)

Or use **Gaussian Random Timer** for more realistic behavior:
- **Constant Delay Offset (ms)**: `1000`
- **Deviation (ms)**: `500`

---

## Stress Testing Strategy

### Phase 1: Baseline Test
- **Threads**: 1
- **Ramp-up**: 1s
- **Loop**: 10
- **Goal**: Verify configuration works

### Phase 2: Light Load
- **Threads**: 10
- **Ramp-up**: 10s
- **Loop**: 20
- **Goal**: Test normal usage

### Phase 3: Medium Load
- **Threads**: 50
- **Ramp-up**: 30s
- **Duration**: 300s (5 min)
- **Goal**: Find performance degradation

### Phase 4: Heavy Load
- **Threads**: 100-200
- **Ramp-up**: 60s
- **Duration**: 600s (10 min)
- **Goal**: Find breaking point

### Phase 5: Spike Test
- **Threads**: 500
- **Ramp-up**: 10s
- **Duration**: 60s
- **Goal**: Test recovery from sudden load

---

## Metrics to Monitor

### JMeter Metrics
- **Response Time**: Should be < 2s for good UX
- **Throughput**: Requests per second
- **Error Rate**: Should be < 1%
- **90th Percentile**: 90% of requests should be under this time

### Bot System Metrics
Monitor your bot server:
```bash
# CPU Usage
top -p $(pgrep -f coordinator_bot)

# Memory Usage
ps aux | grep coordinator_bot

# Network connections
netstat -an | grep ESTABLISHED | wc -l

# RabbitMQ queue depth
sudo rabbitmqctl list_queues
```

---

## Sample JMeter Test Plan XML

Save this as `telegram_bot_stress_test.jmx`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Telegram Bot Stress Test" enabled="true">
      <stringProp name="TestPlan.comments">Stress test for polling-based Telegram bot</stringProp>
      <boolProp name="TestPlan.functional_mode">false</boolProp>
      <boolProp name="TestPlan.serialize_threadgroups">false</boolProp>
      <elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
        <collectionProp name="Arguments.arguments"/>
      </elementProp>
      <stringProp name="TestPlan.user_define_classpath"></stringProp>
    </TestPlan>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="Bot Users" enabled="true">
        <stringProp name="ThreadGroup.on_sample_error">continue</stringProp>
        <elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller" enabled="true">
          <boolProp name="LoopController.continue_forever">false</boolProp>
          <stringProp name="LoopController.loops">5</stringProp>
        </elementProp>
        <stringProp name="ThreadGroup.num_threads">10</stringProp>
        <stringProp name="ThreadGroup.ramp_time">10</stringProp>
        <longProp name="ThreadGroup.start_time">1358788591000</longProp>
        <longProp name="ThreadGroup.end_time">1358788591000</longProp>
        <boolProp name="ThreadGroup.scheduler">false</boolProp>
        <stringProp name="ThreadGroup.duration"></stringProp>
        <stringProp name="ThreadGroup.delay"></stringProp>
      </ThreadGroup>
      <hashTree>
        <Arguments guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
          <collectionProp name="Arguments.arguments">
            <elementProp name="BOT_TOKEN" elementType="Argument">
              <stringProp name="Argument.name">BOT_TOKEN</stringProp>
              <stringProp name="Argument.value">YOUR_BOT_TOKEN_HERE</stringProp>
              <stringProp name="Argument.metadata">=</stringProp>
            </elementProp>
            <elementProp name="CHAT_ID" elementType="Argument">
              <stringProp name="Argument.name">CHAT_ID</stringProp>
              <stringProp name="Argument.value">YOUR_CHAT_ID_HERE</stringProp>
              <stringProp name="Argument.metadata">=</stringProp>
            </elementProp>
          </collectionProp>
        </Arguments>
        <hashTree/>
        <HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="HTTP Header Manager" enabled="true">
          <collectionProp name="HeaderManager.headers">
            <elementProp name="" elementType="Header">
              <stringProp name="Header.name">Content-Type</stringProp>
              <stringProp name="Header.value">application/json</stringProp>
            </elementProp>
          </collectionProp>
        </HeaderManager>
        <hashTree/>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="Send /start Command" enabled="true">
          <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
          <elementProp name="HTTPsampler.Arguments" elementType="Arguments">
            <collectionProp name="Arguments.arguments">
              <elementProp name="" elementType="HTTPArgument">
                <boolProp name="HTTPArgument.always_encode">false</boolProp>
                <stringProp name="Argument.value">{&#xd;
  &quot;chat_id&quot;: &quot;${CHAT_ID}&quot;,&#xd;
  &quot;text&quot;: &quot;/start&quot;&#xd;
}</stringProp>
                <stringProp name="Argument.metadata">=</stringProp>
              </elementProp>
            </collectionProp>
          </elementProp>
          <stringProp name="HTTPSampler.domain">api.telegram.org</stringProp>
          <stringProp name="HTTPSampler.port">443</stringProp>
          <stringProp name="HTTPSampler.protocol">https</stringProp>
          <stringProp name="HTTPSampler.contentEncoding"></stringProp>
          <stringProp name="HTTPSampler.path">/bot${BOT_TOKEN}/sendMessage</stringProp>
          <stringProp name="HTTPSampler.method">POST</stringProp>
          <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
          <boolProp name="HTTPSampler.auto_redirects">false</boolProp>
          <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
          <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
          <stringProp name="HTTPSampler.embedded_url_re"></stringProp>
          <stringProp name="HTTPSampler.connect_timeout"></stringProp>
          <stringProp name="HTTPSampler.response_timeout"></stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
        <ConstantTimer guiclass="ConstantTimerGui" testclass="ConstantTimer" testname="Think Time" enabled="true">
          <stringProp name="ConstantTimer.delay">2000</stringProp>
        </ConstantTimer>
        <hashTree/>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="Search Creator" enabled="true">
          <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
          <elementProp name="HTTPsampler.Arguments" elementType="Arguments">
            <collectionProp name="Arguments.arguments">
              <elementProp name="" elementType="HTTPArgument">
                <boolProp name="HTTPArgument.always_encode">false</boolProp>
                <stringProp name="Argument.value">{&#xd;
  &quot;chat_id&quot;: &quot;${CHAT_ID}&quot;,&#xd;
  &quot;text&quot;: &quot;creator_${__threadNum}&quot;&#xd;
}</stringProp>
                <stringProp name="Argument.metadata">=</stringProp>
              </elementProp>
            </collectionProp>
          </elementProp>
          <stringProp name="HTTPSampler.domain">api.telegram.org</stringProp>
          <stringProp name="HTTPSampler.port">443</stringProp>
          <stringProp name="HTTPSampler.protocol">https</stringProp>
          <stringProp name="HTTPSampler.contentEncoding"></stringProp>
          <stringProp name="HTTPSampler.path">/bot${BOT_TOKEN}/sendMessage</stringProp>
          <stringProp name="HTTPSampler.method">POST</stringProp>
          <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
          <boolProp name="HTTPSampler.auto_redirects">false</boolProp>
          <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
          <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
          <stringProp name="HTTPSampler.embedded_url_re"></stringProp>
          <stringProp name="HTTPSampler.connect_timeout"></stringProp>
          <stringProp name="HTTPSampler.response_timeout"></stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
        <ResultCollector guiclass="ViewResultsFullVisualizer" testclass="ResultCollector" testname="View Results Tree" enabled="true">
          <boolProp name="ResultCollector.error_logging">false</boolProp>
          <objProp>
            <name>saveConfig</name>
            <value class="SampleSaveConfiguration">
              <time>true</time>
              <latency>true</latency>
              <timestamp>true</timestamp>
              <success>true</success>
              <label>true</label>
              <code>true</code>
              <message>true</message>
              <threadName>true</threadName>
              <dataType>true</dataType>
              <encoding>false</encoding>
              <assertions>true</assertions>
              <subresults>true</subresults>
              <responseData>false</responseData>
              <samplerData>false</samplerData>
              <xml>false</xml>
              <fieldNames>true</fieldNames>
              <responseHeaders>false</responseHeaders>
              <requestHeaders>false</requestHeaders>
              <responseDataOnError>false</responseDataOnError>
              <saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage>
              <assertionsResultsToSave>0</assertionsResultsToSave>
              <bytes>true</bytes>
              <sentBytes>true</sentBytes>
              <url>true</url>
              <threadCounts>true</threadCounts>
              <idleTime>true</idleTime>
              <connectTime>true</connectTime>
            </value>
          </objProp>
          <stringProp name="filename"></stringProp>
        </ResultCollector>
        <hashTree/>
        <ResultCollector guiclass="SummaryReport" testclass="ResultCollector" testname="Summary Report" enabled="true">
          <boolProp name="ResultCollector.error_logging">false</boolProp>
          <objProp>
            <name>saveConfig</name>
            <value class="SampleSaveConfiguration">
              <time>true</time>
              <latency>true</latency>
              <timestamp>true</timestamp>
              <success>true</success>
              <label>true</label>
              <code>true</code>
              <message>true</message>
              <threadName>true</threadName>
              <dataType>true</dataType>
              <encoding>false</encoding>
              <assertions>true</assertions>
              <subresults>true</subresults>
              <responseData>false</responseData>
              <samplerData>false</samplerData>
              <xml>false</xml>
              <fieldNames>true</fieldNames>
              <responseHeaders>false</responseHeaders>
              <requestHeaders>false</requestHeaders>
              <responseDataOnError>false</responseDataOnError>
              <saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage>
              <assertionsResultsToSave>0</assertionsResultsToSave>
              <bytes>true</bytes>
              <sentBytes>true</sentBytes>
              <url>true</url>
              <threadCounts>true</threadCounts>
              <idleTime>true</idleTime>
              <connectTime>true</connectTime>
            </value>
          </objProp>
          <stringProp name="filename"></stringProp>
        </ResultCollector>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
```

---

## Running the Test

1. **Install JMeter**: Download from https://jmeter.apache.org/
2. **Open JMeter**: `./bin/jmeter` (GUI mode)
3. **Load Test Plan**: File → Open → `telegram_bot_stress_test.jmx`
4. **Configure Variables**: Update `BOT_TOKEN` and `CHAT_ID`
5. **Run Test**: Click the green "Start" button
6. **Monitor Results**: View the listeners for real-time results

### CLI Mode (for production testing):
```bash
jmeter -n -t telegram_bot_stress_test.jmx -l results.jtl -e -o ./results_dashboard
```

This generates an HTML dashboard in `./results_dashboard/`

---

## Important Notes

⚠️ **Rate Limits**: Telegram has rate limits:
- 30 messages per second to the same chat
- 20 messages per minute to the same group

⚠️ **Bot API Limits**: Telegram Bot API has limits that may affect results

⚠️ **Test Responsibly**: Don't spam your bot or Telegram's API

⚠️ **Use Test Account**: Consider using a test bot token for stress testing

---

## Alternative: Direct Bot Testing (Advanced)

If you want to test your bot directly without going through Telegram:

1. **Create Mock Telegram Server**: Simulate Telegram API locally
2. **Inject Messages**: Directly call your bot's message handlers
3. **Use pytest-benchmark**: For Python-based load testing

Example using Python:
```python
import asyncio
from telegram import Update, Message, Chat, User
from your_bot import handle_message

async def stress_test():
    for i in range(1000):
        # Create mock update
        update = Update(
            update_id=i,
            message=Message(
                message_id=i,
                date=None,
                chat=Chat(id=123, type='private'),
                from_user=User(id=123, is_bot=False, first_name='Test'),
                text='/start'
            )
        )
        await handle_message(update, context)

asyncio.run(stress_test())
```

---

## Questions?

If you need help with:
- Specific command patterns
- Callback query simulation
- Multi-user testing
- Performance optimization

Let me know!
