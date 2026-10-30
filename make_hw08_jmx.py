# ruff: noqa: E501
"""Generate the two JMeter test plans for HW8 (the steps in Jmeter Instructions.pdf).

Run:  python make_hw08_jmx.py

Writes reports/hw08/jmeter/kafka_endpoint.jmx   (POST /api/hw8/entity, via Kafka)
       reports/hw08/jmeter/direct_endpoint.jmx  (POST /api/hw8/entity-direct, no Kafka)

Both plans are the plan from the instructions: Thread Group with 100 threads,
10 s ramp-up, loop count 1; HTTP Request POST to 127.0.0.1:8333 with a JSON body;
HTTP Header Manager (Content-Type: application/json); and the four listeners
(View Results Tree, Summary Report, Aggregate Report, Response Time Graph).
One extra element, a Response Assertion, counts a reply with "success": false as
an error, so Error % means "the operation failed", not only "HTTP failed".
"""

import json
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from hw8 import config

OUT_DIR = config.REPORT_DIR / "jmeter"
THREADS = 100
RAMP_SECONDS = 10
LOOPS = 1

BODY = {
    "operation": config.CREATE_OPERATION,
    "data": {
        "trialTitle": "JMeter Trial ${__threadNum}",
        "sponsor": "Acme Pharma",
        "trial_code": "CT-JM-${__threadNum}",
        "participant_capacity": 100,
        "submitterEmail": "jmeter@example.org",
        "category": "Cardiology",
    },
}

SAVE_CONFIG = (
    "<objProp><name>saveConfig</name>"
    '<value class="SampleSaveConfiguration">'
    "<time>true</time><latency>true</latency><timestamp>true</timestamp>"
    "<success>true</success><label>true</label><code>true</code>"
    "<message>true</message><threadName>true</threadName><dataType>true</dataType>"
    "<encoding>false</encoding><assertions>true</assertions><subresults>true</subresults>"
    "<responseData>false</responseData><samplerData>false</samplerData><xml>false</xml>"
    "<fieldNames>true</fieldNames><responseHeaders>false</responseHeaders>"
    "<requestHeaders>false</requestHeaders><responseDataOnError>false</responseDataOnError>"
    "<saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage>"
    "<assertionsResultsToSave>0</assertionsResultsToSave><bytes>true</bytes>"
    "<sentBytes>true</sentBytes><url>true</url><threadCounts>true</threadCounts>"
    "<idleTime>true</idleTime><connectTime>true</connectTime>"
    "</value></objProp>"
)


def listener(gui_class: str, name: str) -> str:
    """XML for one result listener."""
    return (
        f'<ResultCollector guiclass="{gui_class}" testclass="ResultCollector" '
        f'testname="{name}" enabled="true">'
        '<boolProp name="ResultCollector.error_logging">false</boolProp>'
        f'{SAVE_CONFIG}<stringProp name="filename"></stringProp>'
        "</ResultCollector><hashTree/>"
    )


def build_plan(plan_name: str, sampler_name: str, path: str) -> str:
    """Return the full .jmx text for one endpoint."""
    body = escape(json.dumps(BODY, indent=2))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="{plan_name}" enabled="true">
      <boolProp name="TestPlan.functional_mode">false</boolProp>
      <boolProp name="TestPlan.serialize_threadgroups">false</boolProp>
      <elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
        <collectionProp name="Arguments.arguments"/>
      </elementProp>
    </TestPlan>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="Thread Group" enabled="true">
        <stringProp name="ThreadGroup.on_sample_error">continue</stringProp>
        <elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller" enabled="true">
          <boolProp name="LoopController.continue_forever">false</boolProp>
          <stringProp name="LoopController.loops">{LOOPS}</stringProp>
        </elementProp>
        <stringProp name="ThreadGroup.num_threads">{THREADS}</stringProp>
        <stringProp name="ThreadGroup.ramp_time">{RAMP_SECONDS}</stringProp>
        <boolProp name="ThreadGroup.scheduler">false</boolProp>
        <stringProp name="ThreadGroup.duration"></stringProp>
        <stringProp name="ThreadGroup.delay"></stringProp>
        <boolProp name="ThreadGroup.same_user_on_next_iteration">true</boolProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="{sampler_name}" enabled="true">
          <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
          <elementProp name="HTTPsampler.Arguments" elementType="Arguments">
            <collectionProp name="Arguments.arguments">
              <elementProp name="" elementType="HTTPArgument">
                <boolProp name="HTTPArgument.always_encode">false</boolProp>
                <stringProp name="Argument.value">{body}</stringProp>
                <stringProp name="Argument.metadata">=</stringProp>
              </elementProp>
            </collectionProp>
          </elementProp>
          <stringProp name="HTTPSampler.domain">127.0.0.1</stringProp>
          <stringProp name="HTTPSampler.port">{config.PORT_BASE}</stringProp>
          <stringProp name="HTTPSampler.protocol">http</stringProp>
          <stringProp name="HTTPSampler.path">{path}</stringProp>
          <stringProp name="HTTPSampler.method">POST</stringProp>
          <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
          <boolProp name="HTTPSampler.auto_redirects">false</boolProp>
          <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
          <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
        </HTTPSamplerProxy>
        <hashTree>
          <HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="HTTP Header Manager" enabled="true">
            <collectionProp name="HeaderManager.headers">
              <elementProp name="" elementType="Header">
                <stringProp name="Header.name">Content-Type</stringProp>
                <stringProp name="Header.value">application/json</stringProp>
              </elementProp>
            </collectionProp>
          </HeaderManager>
          <hashTree/>
          <ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname="Response has success true" enabled="true">
            <collectionProp name="Asserion.test_strings">
              <stringProp name="1">"success":\\s*true</stringProp>
            </collectionProp>
            <stringProp name="Assertion.custom_message"></stringProp>
            <stringProp name="Assertion.test_field">Assertion.response_data</stringProp>
            <boolProp name="Assertion.assume_success">false</boolProp>
            <intProp name="Assertion.test_type">2</intProp>
          </ResponseAssertion>
          <hashTree/>
        </hashTree>
        {listener("ViewResultsFullVisualizer", "View Results Tree")}
        {listener("SummaryReport", "Summary Report")}
        {listener("StatVisualizer", "Aggregate Report")}
        {listener("RespTimeGraphVisualizer", "Response Time Graph")}
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""


def main() -> None:
    """Write both plans and check that they are well-formed XML."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    plans = {
        "kafka_endpoint.jmx": build_plan(
            "HW8 Create Clinical Trial via Kafka",
            "Create Clinical Trial via Kafka",
            "/api/hw8/entity",
        ),
        "direct_endpoint.jmx": build_plan(
            "HW8 Create Clinical Trial Direct (no Kafka)",
            "Create Clinical Trial Direct",
            "/api/hw8/entity-direct",
        ),
    }
    for name, text in plans.items():
        ET.fromstring(text.split("?>", 1)[1])  # raises if not well-formed
        (OUT_DIR / name).write_text(text, encoding="utf-8")
        print(f"wrote {(OUT_DIR / name).relative_to(config.REPO_ROOT)}")


if __name__ == "__main__":
    main()
