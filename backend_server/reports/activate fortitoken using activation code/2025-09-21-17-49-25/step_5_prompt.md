# Task 
 When you open app FortiToken Mobile, tap FortiToken Account, you should use activate code 'GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4' to activate a token, name it ai token
# History of Actions 
 {"action": "tap", "xpath": "//android.widget.TextView[@text='Fortinet']", "explanation": "I need to tap the 'Fortinet' option to proceed with the activation process. The xpath of the 'Fortinet' option is //android.widget.TextView[@text='Fortinet'], so I will use it to find the element and tap it.", "result": "success"}
{"action": "input", "bounds": "[10,138][310,185]", "value": "ai token", "explanation": "I need to input the name 'ai token' in the 'Name' field to proceed with the token activation. The bounds of the 'Name' input box are [10,138][310,185], so I will use it to find the input box and input the name.", "result": "success"}
{"action": "input", "bounds": "[10,190][310,237]", "value": "GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4", "explanation": "I need to input the activate code 'GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4' in the 'Key' field to proceed with the token activation. The bounds of the 'Key' input box are [10,190][310,237], so I will use it to find the input box and input the activate code.", "result": "success"}
{"action": "wait", "timeout": 5000, "explanation": "I can see that the page is still loading, so I will wait a moment for the page to change or load.", "result": "success"}
# Source of Page 
 ```yaml
 android.widget.FrameLayout:
- android.view.View:
  - bounds: '[0,616][320,640]'
    class: android.view.View
    clickable: 'false'
    index: '2'
    package: com.fortinet.android.ftm
    resource-id: android:id/navigationBarBackground
    scrollable: 'false'
  android.widget.LinearLayout:
  - android.widget.FrameLayout:
    - android.view.ViewGroup:
      - android.widget.FrameLayout:
        - android.view.ViewGroup:
          - android.widget.ImageButton:
            - bounds: '[0,24][56,80]'
              class: android.widget.ImageButton
              clickable: 'true'
              content-desc: Navigate up
              index: '0'
              package: com.fortinet.android.ftm
              scrollable: 'false'
            android.widget.TextView:
            - bounds: '[72,37][193,67]'
              class: android.widget.TextView
              clickable: 'false'
              index: '1'
              package: com.fortinet.android.ftm
              scrollable: 'false'
              text: Add Account
            bounds: '[0,24][320,80]'
            class: android.view.ViewGroup
            clickable: 'false'
            index: '0'
            package: com.fortinet.android.ftm
            resource-id: com.fortinet.android.ftm:id/action_bar
            scrollable: 'false'
          bounds: '[0,24][320,80]'
          class: android.widget.FrameLayout
          clickable: 'false'
          index: '0'
          package: com.fortinet.android.ftm
          resource-id: com.fortinet.android.ftm:id/action_bar_container
          scrollable: 'false'
        - android.widget.LinearLayout:
          - android.widget.Button:
            - bounds: '[10,252][310,300]'
              class: android.widget.Button
              clickable: 'true'
              index: '3'
              package: com.fortinet.android.ftm
              resource-id: com.fortinet.android.ftm:id/btnAddToken
              scrollable: 'false'
              text: ADD ACCOUNT
            android.widget.EditText:
            - bounds: '[10,138][310,185]'
              class: android.widget.EditText
              clickable: 'true'
              index: '1'
              package: com.fortinet.android.ftm
              resource-id: com.fortinet.android.ftm:id/editTextAccountName
              scrollable: 'false'
              text: ai token
            - bounds: '[10,190][310,237]'
              class: android.widget.EditText
              clickable: 'true'
              index: '2'
              package: com.fortinet.android.ftm
              resource-id: com.fortinet.android.ftm:id/editTextSecretKey
              scrollable: 'false'
              text: GEAD2IZEHWDN2SLTTWIMMFX4FDUFZUSRKGBSL6NUEHTA3IRB6DAG77HOFUCCSFW4
            android.widget.TextView:
            - bounds: '[120,100][199,133]'
              class: android.widget.TextView
              clickable: 'false'
              index: '0'
              package: com.fortinet.android.ftm
              resource-id: com.fortinet.android.ftm:id/textViewAcctType
              scrollable: 'false'
              text: Fortinet
            bounds: '[10,80][310,300]'
            class: android.widget.LinearLayout
            clickable: 'false'
            index: '0'
            package: com.fortinet.android.ftm
            resource-id: com.fortinet.android.ftm:id/layoutAddTokenContent
            scrollable: 'false'
          bounds: '[0,80][320,616]'
          class: android.widget.FrameLayout
          clickable: 'false'
          index: '1'
          package: com.fortinet.android.ftm
          resource-id: android:id/content
          scrollable: 'false'
        bounds: '[0,24][320,616]'
        class: android.view.ViewGroup
        clickable: 'false'
        index: '0'
        package: com.fortinet.android.ftm
        resource-id: com.fortinet.android.ftm:id/decor_content_parent
        scrollable: 'false'
      bounds: '[0,24][320,616]'
      class: android.widget.FrameLayout
      clickable: 'false'
      index: '0'
      package: com.fortinet.android.ftm
      scrollable: 'false'
    bounds: '[0,0][320,616]'
    class: android.widget.LinearLayout
    clickable: 'false'
    index: '0'
    package: com.fortinet.android.ftm
    scrollable: 'false'
  bounds: '[0,0][320,640]'
  class: android.widget.FrameLayout
  clickable: 'false'
  index: '0'
  package: com.fortinet.android.ftm
  scrollable: 'false'
class: hierarchy
index: '0'
 
```