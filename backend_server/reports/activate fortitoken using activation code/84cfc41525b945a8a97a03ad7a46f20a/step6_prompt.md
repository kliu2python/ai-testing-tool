# Task 
 When you open app FortiToken Mobile, tap FortiToken Account, you should use activate code 'GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4' to activate a token, name it ai token
# History of Actions 
 {"action": "tap", "bounds": "[160,543][310,591]", "explanation": "To activate a token using the provided code, I need to enter it manually. The 'ENTER MANUALLY' button is visible on the screen, so I will tap it to proceed with entering the activation code.", "result": "success"}
{"action": "tap", "bounds": "[0,118][320,174]", "explanation": "To activate a token using the provided code, I need to select the Fortinet account. The 'Fortinet' option is visible on the screen, so I will tap it to proceed with the activation process.", "result": "success"}
{"action": "input", "bounds": "[10,138][310,185]", "value": "ai token", "explanation": "I need to input the name 'ai token' for the new account. The input box for the name is visible on the screen, so I will tap it and input the name.", "result": "success"}
{"action": "input", "bounds": "[10,190][310,237]", "value": "GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4", "explanation": "I need to input the activation code 'GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4' in the 'Key' field to activate the token. The input box for the key is visible on the screen, so I will tap it and input the activation code.", "result": "success"}
{"action": "tap", "bounds": "[10,252][310,300]", "explanation": "I need to tap the 'ADD ACCOUNT' button to complete the activation process. The button is visible on the screen, so I will tap it to proceed.", "result": "success"}
# Source of Page 
 ```yaml
 android.widget.FrameLayout:
- android.widget.FrameLayout:
  - android.widget.FrameLayout:
    - android.widget.LinearLayout:
      - android.widget.FrameLayout:
        - android.widget.FrameLayout:
          - android.widget.FrameLayout:
            - android.widget.LinearLayout:
              - android.widget.ProgressBar:
                - bounds: '[40,308][88,356]'
                  class: android.widget.ProgressBar
                  clickable: 'false'
                  index: '0'
                  package: com.fortinet.android.ftm
                  resource-id: android:id/progress
                  scrollable: 'false'
                android.widget.TextView:
                - bounds: '[112,313][280,351]'
                  class: android.widget.TextView
                  clickable: 'false'
                  index: '1'
                  package: com.fortinet.android.ftm
                  resource-id: android:id/message
                  scrollable: 'false'
                  text: "Please wait, this may take a few seconds \u2026"
                bounds: '[16,290][304,374]'
                class: android.widget.LinearLayout
                clickable: 'false'
                index: '0'
                package: com.fortinet.android.ftm
                resource-id: android:id/body
                scrollable: 'false'
              bounds: '[16,290][304,374]'
              class: android.widget.FrameLayout
              clickable: 'false'
              index: '0'
              package: com.fortinet.android.ftm
              scrollable: 'false'
            bounds: '[16,290][304,374]'
            class: android.widget.FrameLayout
            clickable: 'false'
            index: '0'
            package: com.fortinet.android.ftm
            resource-id: android:id/custom
            scrollable: 'false'
          bounds: '[16,290][304,374]'
          class: android.widget.FrameLayout
          clickable: 'false'
          index: '0'
          package: com.fortinet.android.ftm
          resource-id: android:id/customPanel
          scrollable: 'false'
        bounds: '[16,290][304,374]'
        class: android.widget.LinearLayout
        clickable: 'false'
        index: '0'
        package: com.fortinet.android.ftm
        resource-id: android:id/parentPanel
        scrollable: 'false'
      bounds: '[16,290][304,374]'
      class: android.widget.FrameLayout
      clickable: 'false'
      index: '0'
      package: com.fortinet.android.ftm
      resource-id: android:id/content
      scrollable: 'false'
    bounds: '[16,290][304,374]'
    class: android.widget.FrameLayout
    clickable: 'false'
    index: '0'
    package: com.fortinet.android.ftm
    scrollable: 'false'
  bounds: '[0,274][320,390]'
  class: android.widget.FrameLayout
  clickable: 'false'
  index: '0'
  package: com.fortinet.android.ftm
  scrollable: 'false'
class: hierarchy
index: '0'
 
```