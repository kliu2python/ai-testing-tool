# Task 
 When you open app FortiToken Mobile, tap FortiToken Account, you should use activate code 'GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4' to activate a token, name it ai token
# History of Actions 
 {"action": "tap", "bounds": "[160,543][310,591]", "explanation": "To activate a token using the provided code, I need to enter it manually. The 'ENTER MANUALLY' button is visible on the screen, so I will tap it to proceed with entering the activation code.", "result": "success"}
{"action": "tap", "bounds": "[0,118][320,174]", "explanation": "To activate a token using the provided code, I need to select the Fortinet account. The 'Fortinet' option is visible on the screen, so I will tap it to proceed with the activation process.", "result": "success"}
{"action": "input", "bounds": "[10,138][310,185]", "value": "ai token", "explanation": "I need to input the name 'ai token' for the new account. The input box for the name is visible on the screen, so I will tap it and input the name.", "result": "success"}
{"action": "input", "bounds": "[10,190][310,237]", "value": "GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4", "explanation": "I need to input the activation code 'GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4' in the 'Key' field to activate the token. The input box for the key is visible on the screen, so I will tap it and input the activation code.", "result": "success"}
{"action": "tap", "bounds": "[10,252][310,300]", "explanation": "I need to tap the 'ADD ACCOUNT' button to complete the activation process. The button is visible on the screen, so I will tap it to proceed.", "result": "success"}
{"action": "wait", "timeout": 5000, "explanation": "The screen is displaying a loading message, indicating that the activation process is in progress. I will wait for the process to complete.", "result": "success"}
# Source of Page 
 ```yaml
 android.widget.FrameLayout:
- android.widget.FrameLayout:
  - android.widget.FrameLayout:
    - android.widget.LinearLayout:
      - android.widget.FrameLayout:
        - android.widget.ScrollView:
          - android.widget.LinearLayout:
            - android.widget.TextView:
              - bounds: '[16,283][304,383]'
                class: android.widget.TextView
                clickable: 'false'
                index: '0'
                package: com.fortinet.android.ftm
                resource-id: android:id/message
                scrollable: 'false'
                text: 'FortiIdentity Cloud: Token ''FIC4R9IIPKTLD82N'' has expired.
                  Please contact your administrator for a new one, and try again.'
              bounds: '[16,283][304,383]'
              class: android.widget.LinearLayout
              clickable: 'false'
              index: '0'
              package: com.fortinet.android.ftm
              scrollable: 'false'
            bounds: '[16,283][304,383]'
            class: android.widget.ScrollView
            clickable: 'false'
            index: '0'
            package: com.fortinet.android.ftm
            resource-id: android:id/scrollView
            scrollable: 'false'
          bounds: '[16,283][304,383]'
          class: android.widget.FrameLayout
          clickable: 'false'
          index: '1'
          package: com.fortinet.android.ftm
          resource-id: android:id/contentPanel
          scrollable: 'false'
        android.widget.LinearLayout:
        - android.view.View:
          - bounds: '[16,275][304,283]'
            class: android.view.View
            clickable: 'false'
            index: '1'
            package: com.fortinet.android.ftm
            resource-id: android:id/titleDividerNoCustom
            scrollable: 'false'
          android.widget.LinearLayout:
          - android.widget.ImageView:
            - bounds: '[40,243][72,275]'
              class: android.widget.ImageView
              clickable: 'false'
              index: '0'
              package: com.fortinet.android.ftm
              resource-id: android:id/icon
              scrollable: 'false'
            android.widget.TextView:
            - bounds: '[80,244][280,274]'
              class: android.widget.TextView
              clickable: 'false'
              index: '1'
              package: com.fortinet.android.ftm
              resource-id: android:id/alertTitle
              scrollable: 'false'
              text: Failed
            bounds: '[16,225][304,275]'
            class: android.widget.LinearLayout
            clickable: 'false'
            index: '0'
            package: com.fortinet.android.ftm
            resource-id: android:id/title_template
            scrollable: 'false'
          bounds: '[16,225][304,283]'
          class: android.widget.LinearLayout
          clickable: 'false'
          index: '0'
          package: com.fortinet.android.ftm
          resource-id: android:id/topPanel
          scrollable: 'false'
        android.widget.ScrollView:
        - android.widget.LinearLayout:
          - android.widget.Button:
            - bounds: '[228,387][292,435]'
              class: android.widget.Button
              clickable: 'true'
              index: '0'
              package: com.fortinet.android.ftm
              resource-id: android:id/button1
              scrollable: 'false'
              text: OK
            bounds: '[16,383][304,439]'
            class: android.widget.LinearLayout
            clickable: 'false'
            index: '0'
            package: com.fortinet.android.ftm
            scrollable: 'false'
          bounds: '[16,383][304,439]'
          class: android.widget.ScrollView
          clickable: 'false'
          index: '2'
          package: com.fortinet.android.ftm
          resource-id: android:id/buttonPanel
          scrollable: 'false'
        bounds: '[16,225][304,439]'
        class: android.widget.LinearLayout
        clickable: 'false'
        index: '0'
        package: com.fortinet.android.ftm
        resource-id: android:id/parentPanel
        scrollable: 'false'
      bounds: '[16,225][304,439]'
      class: android.widget.FrameLayout
      clickable: 'false'
      index: '0'
      package: com.fortinet.android.ftm
      resource-id: android:id/content
      scrollable: 'false'
    bounds: '[16,225][304,439]'
    class: android.widget.FrameLayout
    clickable: 'false'
    index: '0'
    package: com.fortinet.android.ftm
    scrollable: 'false'
  bounds: '[0,209][320,455]'
  class: android.widget.FrameLayout
  clickable: 'false'
  index: '0'
  package: com.fortinet.android.ftm
  scrollable: 'false'
class: hierarchy
index: '0'
 
```